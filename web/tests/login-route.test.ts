// @vitest-environment node
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as login } from "@/app/api/auth/login/route";
import { POST as logout } from "@/app/api/auth/logout/route";
import { SESSION_COOKIE, verifySessionToken } from "@/lib/session";
import { TEST_PASSWORD, TEST_SECRET, stubServerEnv } from "./support/env";

function form(password: string, next?: string): NextRequest {
  const body = new URLSearchParams({ password, ...(next ? { next } : {}) });
  return new NextRequest("http://localhost:3000/api/auth/login", {
    method: "POST",
    body,
    headers: { "content-type": "application/x-www-form-urlencoded" },
  });
}

describe("POST /api/auth/login", () => {
  beforeEach(() => stubServerEnv());

  it("returns 401 and no cookie for a wrong password", async () => {
    const response = await login(form("wrong"));
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ error: "wrong password" });
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("sets a signed httpOnly lax cookie and redirects for the right password", async () => {
    const response = await login(form(TEST_PASSWORD, "/activities?sport_type=Run"));
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe("/activities?sport_type=Run");
    const cookie = response.cookies.get(SESSION_COOKIE);
    expect(cookie?.httpOnly).toBe(true);
    expect(cookie?.sameSite).toBe("lax");
    expect(cookie?.maxAge).toBe(7 * 24 * 60 * 60);
    expect(cookie?.secure).toBe(false);
    expect(verifySessionToken(cookie?.value, TEST_SECRET, new Date())).toBe(true);
  });

  it("accepts JSON and never redirects off-site", async () => {
    const request = new NextRequest("http://localhost:3000/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ password: TEST_PASSWORD, next: "//evil.example/x" }),
      headers: { "content-type": "application/json" },
    });
    const response = await login(request);
    expect(response.headers.get("location")).toBe("/");
  });

  it("marks the cookie secure in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const response = await login(form(TEST_PASSWORD));
    expect(response.cookies.get(SESSION_COOKIE)?.secure).toBe(true);
  });

  it("lets DASHBOARD_COOKIE_SECURE override the default", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("DASHBOARD_COOKIE_SECURE", "false");
    const response = await login(form(TEST_PASSWORD));
    expect(response.cookies.get(SESSION_COOKIE)?.secure).toBe(false);
  });

  it("refuses to run with a short session secret", async () => {
    vi.stubEnv("DASHBOARD_SESSION_SECRET", "short");
    await expect(login(form(TEST_PASSWORD))).rejects.toThrow(/at least 32/);
  });
});

describe("POST /api/auth/logout", () => {
  it("clears the cookie and goes to /login", () => {
    const response = logout();
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe("/login");
    expect(response.headers.get("set-cookie")).toMatch(new RegExp(`${SESSION_COOKIE}=;`));
  });
});
