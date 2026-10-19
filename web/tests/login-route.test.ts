// @vitest-environment node
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as login } from "@/app/api/auth/login/route";
import { POST as logout } from "@/app/api/auth/logout/route";
import { CSRF_COOKIE } from "@/lib/csrf-cookie";
import { SESSION_COOKIE, SESSION_MAX_AGE_S, openSession } from "@/lib/session";
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
const SIGNED_IN = { token: TEST_TOKEN, expires_at: "2026-11-18T12:00:00Z", user: { id: 2 } };

function form(password: string, next?: string): NextRequest {
  const body = new URLSearchParams({ email: TEST_EMAIL, password, ...(next ? { next } : {}) });
  return new NextRequest("http://localhost:3000/api/auth/login", {
    method: "POST",
    body,
    headers: { "content-type": "application/x-www-form-urlencoded", "user-agent": "phone" },
  });
}

describe("POST /api/auth/login", () => {
  beforeEach(() => {
    stubServerEnv();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("asks the API and answers its 401 without a cookie", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "invalid email or password" }, 401));
    const response = await login(form("wrong"));
    expect(response.status).toBe(401);
    expect(response.headers.get("set-cookie")).toBeNull();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe("http://api.test:8000/v1/auth/login");
    expect(JSON.parse(String(init?.body))).toEqual({ email: TEST_EMAIL, password: "wrong" });
    expect(new Headers(init?.headers).get("authorization")).toBeNull();
  });

  it("seals the API token into an httpOnly lax cookie and redirects", async () => {
    fetchMock.mockResolvedValue(jsonResponse(SIGNED_IN));
    const response = await login(form(TEST_PASSWORD, "/activities?sport_type=Run"));
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe("/activities?sport_type=Run");
    const cookie = response.cookies.get(SESSION_COOKIE);
    expect(cookie?.httpOnly).toBe(true);
    expect(cookie?.sameSite).toBe("lax");
    expect(cookie?.maxAge).toBe(SESSION_MAX_AGE_S);
    expect(cookie?.secure).toBe(false);
    expect(cookie?.value).not.toContain(TEST_TOKEN);
    expect(openSession(cookie?.value, TEST_SECRET, new Date())?.token).toBe(TEST_TOKEN);
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get("user-agent")).toBe("phone");
  });

  it("issues a readable strict CSRF cookie with the session", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(SIGNED_IN));
    const response = await login(form(TEST_PASSWORD));
    const csrf = response.cookies.get(CSRF_COOKIE);
    expect(csrf?.value).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(csrf?.httpOnly).toBe(false);
    expect(csrf?.sameSite).toBe("strict");
    const again = await login(form(TEST_PASSWORD));
    expect(again.cookies.get(CSRF_COOKIE)?.value).not.toBe(csrf?.value);
  });

  it("accepts JSON and never redirects off-site", async () => {
    fetchMock.mockResolvedValue(jsonResponse(SIGNED_IN));
    const request = new NextRequest("http://localhost:3000/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: TEST_EMAIL, password: TEST_PASSWORD, next: "//evil.example/x" }),
      headers: { "content-type": "application/json" },
    });
    const response = await login(request);
    expect(response.headers.get("location")).toBe("/");
  });

  it("passes the API's lockout on with Retry-After", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: "too many failed sign-ins" }, 429, { "retry-after": "600" }),
    );
    const response = await login(form(TEST_PASSWORD));
    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("600");
  });

  it("marks the cookie secure in production and lets DASHBOARD_COOKIE_SECURE override", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(SIGNED_IN));
    vi.stubEnv("NODE_ENV", "production");
    expect((await login(form(TEST_PASSWORD))).cookies.get(SESSION_COOKIE)?.secure).toBe(true);
    vi.stubEnv("DASHBOARD_COOKIE_SECURE", "false");
    expect((await login(form(TEST_PASSWORD))).cookies.get(SESSION_COOKIE)?.secure).toBe(false);
  });

  it("refuses to run with a short session secret", async () => {
    fetchMock.mockResolvedValue(jsonResponse(SIGNED_IN));
    vi.stubEnv("DASHBOARD_SESSION_SECRET", "short");
    await expect(login(form(TEST_PASSWORD))).rejects.toThrow(/at least 32/);
  });
});

describe("POST /api/auth/logout", () => {
  beforeEach(() => {
    stubServerEnv();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("revokes the API session, clears the cookies and goes to /login", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const request = new NextRequest("http://localhost:3000/api/auth/logout", {
      method: "POST",
      headers: { cookie: sessionCookie() },
    });
    const response = await logout(request);
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe("/login");
    expect(response.headers.get("set-cookie")).toMatch(new RegExp(`${SESSION_COOKIE}=;`));
    expect(response.headers.get("set-cookie")).toMatch(new RegExp(`${CSRF_COOKIE}=;`));
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe("http://api.test:8000/v1/auth/logout");
    expect(new Headers(init?.headers).get("authorization")).toBe(`Bearer ${TEST_TOKEN}`);
  });

  it("still signs out the browser without a session", async () => {
    const request = new NextRequest("http://localhost:3000/api/auth/logout", { method: "POST" });
    const response = await logout(request);
    expect(response.status).toBe(303);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
