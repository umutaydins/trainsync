import { NextResponse, type NextRequest } from "next/server";

import { createCsrfToken, isCsrfToken, setCsrfCookie } from "@/lib/csrf";
import { CSRF_COOKIE } from "@/lib/csrf-cookie";
import { SESSION_COOKIE, cookieSecureFromEnv, openSession } from "@/lib/session";

/** Paths reachable without a session (exact). */
const PUBLIC_PATHS = new Set([
  "/login",
  "/register",
  "/reset-password",
  "/forgot-password",
  "/privacy",
  "/terms",
  "/api/auth/login",
  "/api/auth/register",
  "/api/auth/registration",
  "/api/auth/reset",
  "/api/health",
]);

/**
 * Access gate: every page and BFF call needs a session cookie that opens (sealed, unexpired; the
 * API still decides whether the token inside is valid). A signed-in request
 * without a well-formed CSRF cookie gets one, so pages can always send mutations (ADR 0011).
 */
export function proxy(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC_PATHS.has(pathname)) return NextResponse.next();

  const secret = process.env.DASHBOARD_SESSION_SECRET ?? "";
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (openSession(token, secret, new Date()) !== null) {
    const response = NextResponse.next();
    if (!isCsrfToken(request.cookies.get(CSRF_COOKIE)?.value)) {
      setCsrfCookie(response, createCsrfToken(), cookieSecureFromEnv());
    }
    return response;
  }

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "not signed in" }, { status: 401 });
  }
  const login = new URL("/login", request.url);
  if (pathname !== "/") login.searchParams.set("next", `${pathname}${search}`);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except Next's own static assets, the favicon and the PWA manifest and icons (the
  // browser fetches the manifest without cookies; none of these carry data).
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg|manifest.webmanifest|icons/).*)"],
};
