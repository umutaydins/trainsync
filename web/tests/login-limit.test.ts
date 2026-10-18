// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST as login } from "@/app/api/auth/login/route";
import { LOGIN_MAX_FAILURES, LOGIN_WINDOW_MS, LoginRateLimiter, clientIp } from "@/lib/login-limit";
import { SESSION_COOKIE } from "@/lib/session";
import { TEST_PASSWORD, stubServerEnv } from "./support/env";

function attempt(password: string, ip: string): Promise<Response> {
  return login(
    new NextRequest("http://localhost:3000/api/auth/login", {
      method: "POST",
      body: new URLSearchParams({ password }),
      headers: { "content-type": "application/x-www-form-urlencoded", "x-forwarded-for": ip },
    }),
  );
}

async function failTimes(ip: string, times: number): Promise<void> {
  for (let i = 0; i < times; i += 1) expect((await attempt("wrong", ip)).status).toBe(401);
}

describe("login rate limit (route)", () => {
  beforeEach(() => {
    stubServerEnv();
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-18T09:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  it("answers 429 with Retry-After after 5 failures, even for the right password", async () => {
    await failTimes("203.0.113.1", LOGIN_MAX_FAILURES);
    const blocked = await attempt(TEST_PASSWORD, "203.0.113.1");
    expect(blocked.status).toBe(429);
    expect(blocked.headers.get("retry-after")).toBe(String(LOGIN_WINDOW_MS / 1000));
    expect(await blocked.json()).toEqual({ error: "too many failed attempts" });
    expect(blocked.headers.get("set-cookie")).toBeNull();
  });

  it("counts per address: another address can still sign in", async () => {
    await failTimes("203.0.113.2", LOGIN_MAX_FAILURES);
    const other = await attempt(TEST_PASSWORD, "203.0.113.3");
    expect(other.status).toBe(303);
    expect(other.headers.get("set-cookie")).toContain(SESSION_COOKIE);
  });

  it("lets the address try again once the 15-minute window has passed", async () => {
    await failTimes("203.0.113.4", LOGIN_MAX_FAILURES);
    vi.setSystemTime(Date.now() + 10 * 60 * 1000);
    const later = await attempt(TEST_PASSWORD, "203.0.113.4");
    expect(later.status).toBe(429);
    expect(later.headers.get("retry-after")).toBe(String(5 * 60));
    vi.setSystemTime(Date.now() + 5 * 60 * 1000);
    expect((await attempt(TEST_PASSWORD, "203.0.113.4")).status).toBe(303);
  });

  it("a successful login clears earlier failures", async () => {
    await failTimes("203.0.113.5", LOGIN_MAX_FAILURES - 1);
    expect((await attempt(TEST_PASSWORD, "203.0.113.5")).status).toBe(303);
    await failTimes("203.0.113.5", LOGIN_MAX_FAILURES - 1);
    expect((await attempt(TEST_PASSWORD, "203.0.113.5")).status).toBe(303);
  });
});

describe("LoginRateLimiter", () => {
  it("blocks only after the limit and reports the remaining seconds", () => {
    let now = 0;
    const limiter = new LoginRateLimiter(2, 60_000, () => now);
    limiter.recordFailure("a");
    expect(limiter.retryAfterS("a")).toBeNull();
    limiter.recordFailure("a");
    expect(limiter.retryAfterS("a")).toBe(60);
    now = 59_500;
    expect(limiter.retryAfterS("a")).toBe(1);
    now = 60_000;
    expect(limiter.retryAfterS("a")).toBeNull();
  });

  it("starts a new window after the old one expires", () => {
    let now = 0;
    const limiter = new LoginRateLimiter(2, 60_000, () => now);
    limiter.recordFailure("a");
    now = 61_000;
    limiter.recordFailure("a");
    expect(limiter.retryAfterS("a")).toBeNull();
  });
});

describe("clientIp", () => {
  it("uses the last X-Forwarded-For entry, the one the nearest hop added", () => {
    expect(clientIp(new Headers({ "x-forwarded-for": "198.51.100.7, 203.0.113.9" }))).toBe("203.0.113.9");
    expect(clientIp(new Headers({ "x-forwarded-for": "203.0.113.9" }))).toBe("203.0.113.9");
    expect(clientIp(new Headers())).toBe("unknown");
  });
});
