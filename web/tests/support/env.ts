import { vi } from "vitest";

export const TEST_API_KEY = "test-api-key-canary-0123456789";
export const TEST_PASSWORD = "correct horse battery staple";
export const TEST_SECRET = "test-session-secret-0123456789abcdef";

export function stubServerEnv(overrides: Record<string, string> = {}): void {
  const values: Record<string, string> = {
    TRAINSYNC_API_URL: "http://api.test:8000",
    TRAINSYNC_API_KEY: TEST_API_KEY,
    DASHBOARD_PASSWORD: TEST_PASSWORD,
    DASHBOARD_SESSION_SECRET: TEST_SECRET,
    TRAINSYNC_PUBLIC_API_URL: "http://localhost:8000",
    WEB_PUBLIC_URL: "http://localhost:3000",
    ...overrides,
  };
  for (const [key, value] of Object.entries(values)) vi.stubEnv(key, value);
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}
