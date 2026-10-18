import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, verifySessionToken } from "@/lib/session";

/** Paths reachable without a session (exact). */
const PUBLIC_PATHS = new Set(["/login", "/api/auth/login", "/api/health"]);

/** Access gate: every page and BFF call needs a valid signed session cookie. */
export function proxy(request: NextRequest): NextResponse {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC_PATHS.has(pathname)) return NextResponse.next();

  const secret = process.env.DASHBOARD_SESSION_SECRET ?? "";
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (secret && verifySessionToken(token, secret, new Date())) return NextResponse.next();

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "not signed in" }, { status: 401 });
  }
  const login = new URL("/login", request.url);
  if (pathname !== "/") login.searchParams.set("next", `${pathname}${search}`);
  return NextResponse.redirect(login);
}

export const config = {
  // Everything except Next's own static assets and the favicon.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg).*)"],
};
