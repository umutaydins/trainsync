import { NextResponse, type NextRequest } from "next/server";

import { createCsrfToken, setCsrfCookie } from "@/lib/csrf";
import { serverEnv } from "@/lib/env";
import { clientIp, loginLimiter } from "@/lib/login-limit";
import {
  SESSION_COOKIE,
  SESSION_MAX_AGE_S,
  createSessionToken,
  passwordMatches,
  safeNextPath,
  seeOther,
} from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Form or JSON body `{password, next?}`. 303 to `next` with a session cookie, or 401.
 * 429 with `Retry-After` after LOGIN_MAX_FAILURES failures from one address in LOGIN_WINDOW_MS,
 * even for the right password, so a blocked address cannot keep guessing.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const ip = clientIp(request.headers);
  const retryAfter = loginLimiter.retryAfterS(ip);
  if (retryAfter !== null) {
    return NextResponse.json(
      { error: "too many failed attempts" },
      { status: 429, headers: { "Retry-After": String(retryAfter) } },
    );
  }
  const { password, next } = await readCredentials(request);
  const env = serverEnv();
  if (!passwordMatches(password, env.dashboardPassword)) {
    loginLimiter.recordFailure(ip);
    return NextResponse.json({ error: "wrong password" }, { status: 401 });
  }
  loginLimiter.reset(ip);
  const response = new NextResponse(null, seeOther(safeNextPath(next)));
  response.cookies.set(SESSION_COOKIE, createSessionToken(env.sessionSecret, new Date()), {
    httpOnly: true,
    secure: env.cookieSecure,
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE_S,
  });
  // A fresh CSRF token per session; proxy.ts re-issues it if the cookie goes missing.
  setCsrfCookie(response, createCsrfToken(), env.cookieSecure);
  return response;
}

async function readCredentials(request: NextRequest): Promise<{ password: string; next: string }> {
  const type = request.headers.get("content-type") ?? "";
  if (type.includes("application/json")) {
    const body: unknown = await request.json().catch(() => ({}));
    const record = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
    return { password: String(record.password ?? ""), next: String(record.next ?? "/") };
  }
  const form = await request.formData().catch(() => new FormData());
  return { password: String(form.get("password") ?? ""), next: String(form.get("next") ?? "/") };
}
