// @vitest-environment node
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { proxy } from "@/proxy";
import { CSRF_COOKIE } from "@/lib/csrf-cookie";
import { SESSION_COOKIE, createSessionToken } from "@/lib/session";
import { TEST_SECRET, stubServerEnv } from "./support/env";

function request(path: string, cookie?: string, extraCookie = ""): NextRequest {
  const parts = [cookie ? `${SESSION_COOKIE}=${cookie}` : "", extraCookie].filter(Boolean);
  const headers = parts.length > 0 ? { cookie: parts.join("; ") } : undefined;
  return new NextRequest(`http://localhost:3000${path}`, { headers });
}

describe("access gate", () => {
  beforeEach(() => stubServerEnv());

  it.each(["/", "/activities", "/activities/123", "/sync", "/anything/else"])(
    "redirects %s to /login without a session",
    (path) => {
      const response = proxy(request(path));
      expect(response.status).toBe(307);
      const location = new URL(response.headers.get("location") ?? "");
      expect(location.pathname).toBe("/login");
      if (path !== "/") expect(location.searchParams.get("next")).toBe(path);
    },
  );

  it("keeps the query string in `next`", () => {
    const response = proxy(request("/activities?sport_type=Run"));
    const location = new URL(response.headers.get("location") ?? "");
    expect(location.searchParams.get("next")).toBe("/activities?sport_type=Run");
  });

  it("answers BFF calls without a session with 401 JSON", async () => {
    const response = proxy(request("/api/ts/v1/activities"));
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ error: "not signed in" });
  });

  it("rejects a forged or expired cookie", () => {
    expect(proxy(request("/", "4102444800.forgedforgedforgedforgedforgedforgedforged1")).status).toBe(307);
    const expired = createSessionToken(TEST_SECRET, new Date("2020-01-01T00:00:00Z"));
    expect(proxy(request("/", expired)).status).toBe(307);
  });

  it.each(["/login", "/api/auth/login", "/api/health"])("lets %s through", (path) => {
    expect(proxy(request(path)).headers.get("x-middleware-next")).toBe("1");
  });

  it("lets a valid session through", () => {
    const token = createSessionToken(TEST_SECRET, new Date());
    for (const path of ["/", "/sync", "/api/ts/v1/sync/status"]) {
      expect(proxy(request(path, token)).headers.get("x-middleware-next")).toBe("1");
    }
  });

  it("issues a CSRF cookie to a signed-in request that has none", () => {
    const token = createSessionToken(TEST_SECRET, new Date());
    const response = proxy(request("/training", token));
    expect(response.headers.get("x-middleware-next")).toBe("1");
    const csrf = response.cookies.get(CSRF_COOKIE);
    expect(csrf?.value).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(csrf?.httpOnly).toBe(false);
    expect(csrf?.sameSite).toBe("strict");
    expect(csrf?.secure).toBe(false);
    expect(csrf?.path).toBe("/");
  });

  it("keeps an existing CSRF cookie and replaces a malformed one", () => {
    const token = createSessionToken(TEST_SECRET, new Date());
    const existing = `${CSRF_COOKIE}=${"k".repeat(43)}`;
    expect(proxy(request("/", token, existing)).cookies.get(CSRF_COOKIE)).toBeUndefined();
    const fixed = proxy(request("/", token, `${CSRF_COOKIE}=bad`)).cookies.get(CSRF_COOKIE);
    expect(fixed?.value).toMatch(/^[A-Za-z0-9_-]{43}$/);
  });

  it("marks the CSRF cookie secure in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    const token = createSessionToken(TEST_SECRET, new Date());
    expect(proxy(request("/", token)).cookies.get(CSRF_COOKIE)?.secure).toBe(true);
  });

  it("issues no CSRF cookie without a session", () => {
    expect(proxy(request("/login")).cookies.get(CSRF_COOKIE)).toBeUndefined();
    expect(proxy(request("/")).cookies.get(CSRF_COOKIE)).toBeUndefined();
  });
});
