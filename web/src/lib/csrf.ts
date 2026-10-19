import { randomBytes, timingSafeEqual } from "node:crypto";

import type { NextResponse } from "next/server";

import { CSRF_COOKIE, CSRF_HEADER } from "@/lib/csrf-cookie";
import { originOf } from "@/lib/origins";
import { SESSION_MAX_AGE_S } from "@/lib/session";

// No `server-only` here: proxy.ts imports this module, like it imports lib/session.ts.

const TOKEN = /^[A-Za-z0-9_-]{43}$/;

/** 32 random bytes, base64url (43 characters). */
export function createCsrfToken(): string {
  return randomBytes(32).toString("base64url");
}

/**
 * Double-submit cookie: readable by the page (not httpOnly) so `lib/mutate.ts` can copy it into
 * `X-CSRF-Token`; `sameSite=strict` so other sites never send it.
 */
export function setCsrfCookie(response: NextResponse, token: string, secure: boolean): void {
  response.cookies.set(CSRF_COOKIE, token, {
    httpOnly: false,
    secure,
    sameSite: "strict",
    path: "/",
    maxAge: SESSION_MAX_AGE_S,
  });
}

export function isCsrfToken(value: string | undefined): value is string {
  return value !== undefined && TOKEN.test(value);
}

export type CsrfFailure = "origin" | "token";

/**
 * Checks a mutation: the request's `Origin` (or, without one, its `Referer`) must be the
 * dashboard's own origin, and `X-CSRF-Token` must equal the CSRF cookie (constant-time).
 * Returns the failed check, or null when both pass.
 */
export function checkCsrf(
  headers: Headers,
  cookieToken: string | undefined,
  allowed: string | readonly string[],
): CsrfFailure | null {
  if (!sameOrigin(headers, typeof allowed === "string" ? [allowed] : allowed)) return "origin";
  const headerToken = headers.get(CSRF_HEADER) ?? undefined;
  if (!isCsrfToken(cookieToken) || !isCsrfToken(headerToken)) return "token";
  return timingSafeEqual(Buffer.from(cookieToken), Buffer.from(headerToken)) ? null : "token";
}

/**
 * The origin half of `checkCsrf`, for the routes used before a session (and its CSRF cookie)
 * exists: register and password reset.
 */
export function checkCsrfOrigin(headers: Headers, allowed: readonly string[]): boolean {
  return sameOrigin(headers, allowed);
}

function sameOrigin(headers: Headers, allowed: readonly string[]): boolean {
  const expected = new Set(allowed.map(originOf).filter((o): o is string => o !== null));
  if (expected.size === 0) return false;
  const origin = headers.get("origin");
  // `Origin: null` (sandboxed frames, some redirects) is a mismatch, not a missing header.
  if (origin !== null) return expected.has(origin);
  const referer = headers.get("referer");
  const refererOrigin = referer === null ? null : originOf(referer);
  return refererOrigin !== null && expected.has(refererOrigin);
}
