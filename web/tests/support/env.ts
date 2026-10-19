import { vi } from "vitest";

import { SESSION_COOKIE, sealSession } from "@/lib/session";

/** The user's API session token inside the test session cookie; must never reach a response. */
export const TEST_TOKEN = "test-session-token-canary-0123456789";
export const TEST_EMAIL = "runner@example.com";
export const TEST_PASSWORD = "correct horse battery staple";
export const TEST_SECRET = "test-session-secret-0123456789abcdef";
const DAY_S = 24 * 60 * 60;

export function stubServerEnv(overrides: Record<string, string> = {}): void {
  const values: Record<string, string> = {
    TRAINSYNC_API_URL: "http://api.test:8000",
    DASHBOARD_SESSION_SECRET: TEST_SECRET,
    WEB_PUBLIC_URL: "http://localhost:3000",
    ...overrides,
  };
  for (const [key, value] of Object.entries(values)) vi.stubEnv(key, value);
}

/** A `Cookie` header pair for a signed-in browser. */
export function sessionCookie(token = TEST_TOKEN, now = new Date()): string {
  const expiresAt = Math.floor(now.getTime() / 1000) + DAY_S;
  return `${SESSION_COOKIE}=${sealSession({ token, expiresAt }, TEST_SECRET)}`;
}

export function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}
