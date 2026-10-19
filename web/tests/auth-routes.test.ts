// @vitest-environment node
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DELETE as deleteAccount } from "@/app/api/account/route";
import { POST as register } from "@/app/api/auth/register/route";
import { GET as registration } from "@/app/api/auth/registration/route";
import { POST as reset } from "@/app/api/auth/reset/route";
import { GET as connect } from "@/app/api/strava/connect/route";
import { CSRF_COOKIE } from "@/lib/csrf-cookie";
import { SESSION_COOKIE, openSession } from "@/lib/session";
import {
  TEST_EMAIL,
  TEST_PASSWORD,
  TEST_SECRET,
  TEST_TOKEN,
  jsonResponse,
  sessionCookie,
  stubServerEnv,
} from "./support/env";

const fetchMock = vi.fn<typeof fetch>();
const ORIGIN = "http://localhost:3000";
const CSRF = "c".repeat(43);

function post(path: string, body: unknown, headers: Record<string, string> = {}): NextRequest {
  return new NextRequest(`${ORIGIN}${path}`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json", origin: ORIGIN, ...headers },
  });
}

function calls(): { url: string; body: unknown; auth: string | null }[] {
  return fetchMock.mock.calls.map(([url, init]) => ({
    url: String(url),
    body: init?.body ? JSON.parse(String(init.body)) : null,
    auth: new Headers(init?.headers).get("authorization"),
  }));
}

describe("account route handlers (P8.7)", () => {
  beforeEach(() => {
    stubServerEnv();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("registers, then signs the new account in", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ id: 2, email: TEST_EMAIL }, 201))
      .mockResolvedValueOnce(jsonResponse({ token: TEST_TOKEN, expires_at: "x", user: {} }))
      .mockResolvedValueOnce(jsonResponse({ lang: "tr" }))
      .mockResolvedValueOnce(jsonResponse({ timezone: "Europe/Istanbul" }));
    const body = {
      email: TEST_EMAIL,
      password: TEST_PASSWORD,
      invite_code: "abc",
      next: "/training",
      role: "owner",
    };
    const response = await register(post("/api/auth/register", body));
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe("/training");
    const cookie = response.cookies.get(SESSION_COOKIE);
    expect(openSession(cookie?.value, TEST_SECRET, new Date())?.token).toBe(TEST_TOKEN);
    const [created, signedIn] = calls();
    expect(created?.url).toBe("http://api.test:8000/v1/auth/register");
    expect(created?.body).toEqual({ email: TEST_EMAIL, password: TEST_PASSWORD, invite_code: "abc" });
    expect(signedIn?.url).toBe("http://api.test:8000/v1/auth/login");
    // The new account's language and zone, for the first render (ADR 0039).
    expect(response.cookies.get("lang")?.value).toBe("tr");
    expect(response.cookies.get("tz")?.value).toBe("Europe/Istanbul");
  });

  it("passes the API's refusal on and refuses other origins", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "an invite code is required" }, 400));
    const refused = await register(post("/api/auth/register", { email: TEST_EMAIL, password: TEST_PASSWORD }));
    expect(refused.status).toBe(400);
    expect(refused.headers.get("set-cookie")).toBeNull();
    const cross = await register(
      post("/api/auth/register", { email: TEST_EMAIL }, { origin: "https://evil.example" }),
    );
    expect(cross.status).toBe(403);
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("tells the register page the registration mode", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ mode: "invite" }));
    const response = await registration();
    expect(await response.json()).toEqual({ mode: "invite" });
  });

  it("resets a password with a token from the owner's link", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const response = await reset(post("/api/auth/reset", { token: "t0k", password: TEST_PASSWORD }));
    expect(response.status).toBe(204);
    expect(calls()[0]).toEqual({
      url: "http://api.test:8000/v1/auth/reset",
      body: { token: "t0k", password: TEST_PASSWORD },
      auth: null,
    });
  });

  it("connects Strava through an authorize URL the API signs for this user", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ url: "https://www.strava.com/oauth/authorize?x=1" }));
    const request = new NextRequest(`${ORIGIN}/api/strava/connect`, {
      headers: { cookie: sessionCookie() },
    });
    const response = await connect(request);
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe("https://www.strava.com/oauth/authorize?x=1");
    const [call] = calls();
    expect(call?.url).toBe(
      "http://api.test:8000/v1/me/strava/authorize-url?return_to=http%3A%2F%2Flocalhost%3A3000%2Fsync",
    );
    expect(call?.auth).toBe(`Bearer ${TEST_TOKEN}`);
    const anonymous = await connect(new NextRequest(`${ORIGIN}/api/strava/connect`));
    expect(anonymous.headers.get("location")).toBe("/login");
  });

  it("returns Strava to an allowlisted page only", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ url: "https://www.strava.com/oauth/authorize?x=1" }));
    const at = (returnTo: string) =>
      new NextRequest(`${ORIGIN}/api/strava/connect?return_to=${encodeURIComponent(returnTo)}`, {
        headers: { cookie: sessionCookie() },
      });
    await connect(at("/onboarding"));
    await connect(at("https://evil.example/x"));
    await connect(at("/me/connections"));
    const [onboarding, evil, settings] = calls();
    expect(new URL(onboarding?.url ?? "").searchParams.get("return_to")).toBe("http://localhost:3000/onboarding");
    expect(new URL(settings?.url ?? "").searchParams.get("return_to")).toBe("http://localhost:3000/me/connections");
    expect(new URL(evil?.url ?? "").searchParams.get("return_to")).toBe("http://localhost:3000/sync");
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "boom" }, 500));
    expect((await connect(at("/onboarding"))).headers.get("location")).toBe("/onboarding");
  });

  it("deletes the account and ends the browser session", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const request = new NextRequest(`${ORIGIN}/api/account`, {
      method: "DELETE",
      body: JSON.stringify({ password: TEST_PASSWORD }),
      headers: {
        "content-type": "application/json",
        origin: ORIGIN,
        "x-csrf-token": CSRF,
        cookie: `${sessionCookie()}; ${CSRF_COOKIE}=${CSRF}`,
      },
    });
    const response = await deleteAccount(request);
    expect(response.status).toBe(204);
    expect(response.headers.get("set-cookie")).toMatch(new RegExp(`${SESSION_COOKIE}=;`));
    expect(calls()[0]).toMatchObject({ url: "http://api.test:8000/v1/me", auth: `Bearer ${TEST_TOKEN}` });
    const noCsrf = await deleteAccount(
      new NextRequest(`${ORIGIN}/api/account`, { method: "DELETE", headers: { origin: ORIGIN } }),
    );
    expect(noCsrf.status).toBe(403);
  });
});
