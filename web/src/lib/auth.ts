import "server-only";

import { cookies } from "next/headers";
import type { NextResponse } from "next/server";

import { CSRF_COOKIE } from "@/lib/csrf-cookie";
import { createCsrfToken, setCsrfCookie } from "@/lib/csrf";
import { serverEnv } from "@/lib/env";
import { SESSION_COOKIE, SESSION_MAX_AGE_S, openSession, sealSession } from "@/lib/session";

/** The signed-in user's API session token from the request cookie, or null. */
export async function sessionToken(): Promise<string | null> {
  const store = await cookies();
  return tokenFromCookie(store.get(SESSION_COOKIE)?.value);
}

export function tokenFromCookie(value: string | undefined): string | null {
  return openSession(value, serverEnv().sessionSecret, new Date())?.token ?? null;
}

/** Start a browser session for an API session token (login, register) with a fresh CSRF token. */
export function startSession(response: NextResponse, token: string, now: Date = new Date()): void {
  const env = serverEnv();
  const expiresAt = Math.floor(now.getTime() / 1000) + SESSION_MAX_AGE_S;
  response.cookies.set(SESSION_COOKIE, sealSession({ token, expiresAt }, env.sessionSecret), {
    httpOnly: true,
    secure: env.cookieSecure,
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE_S,
  });
  setCsrfCookie(response, createCsrfToken(), env.cookieSecure);
}

export function endSession(response: NextResponse): void {
  response.cookies.delete(SESSION_COOKIE);
  response.cookies.delete(CSRF_COOKIE);
}
