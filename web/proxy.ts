import { NextResponse, type NextRequest } from "next/server";

import { createCsrfToken, isCsrfToken, setCsrfCookie } from "@/lib/csrf";
import { CSRF_COOKIE } from "@/lib/csrf-cookie";
import { SESSION_COOKIE, cookieSecureFromEnv, verifySessionToken } from "@/lib/session";

/** Paths reachable without a session (exact). */
const PUBLIC_PATHS = new Set(["/login", "/api/auth/login", "/api/health"]);

/**
 * Access gate: every page and BFF call needs a valid signed session cookie. A signed-in request
 * without a well-formed CSRF cookie gets one, so pages can always send mutations (ADR 0011).
 */
export function proxy(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC_PATHS.has(pathname)) return NextResponse.next();

  const secret = process.env.DASHBOARD_SESSION_SECRET ?? "";
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (secret && verifySessionToken(token, secret, new Date())) {
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
