import { createHash, createHmac, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "ts_session";
export const SESSION_MAX_AGE_S = 7 * 24 * 60 * 60;

/**
 * Whether cookies get `Secure`: `DASHBOARD_COOKIE_SECURE` if set, otherwise only in production.
 * Here rather than in lib/env.ts because proxy.ts needs it and must not import server-only modules.
 */
export function cookieSecureFromEnv(): boolean {
  const override = process.env.DASHBOARD_COOKIE_SECURE;
  return override ? override === "true" : process.env.NODE_ENV === "production";
}

/** `<expires_at_unix>.<hmac-sha256(secret, "v1.<expires_at_unix>")>` (base64url). */
export function createSessionToken(secret: string, now: Date): string {
  const expiresAt = Math.floor(now.getTime() / 1000) + SESSION_MAX_AGE_S;
  return `${expiresAt}.${sign(secret, expiresAt)}`;
}

export function verifySessionToken(token: string | undefined, secret: string, now: Date): boolean {
  if (!token) return false;
  const match = /^(\d{1,12})\.([A-Za-z0-9_-]{43})$/.exec(token);
  if (!match) return false;
  const expiresAt = Number(match[1]);
  if (!safeEqual(match[2] ?? "", sign(secret, expiresAt))) return false;
  return expiresAt > Math.floor(now.getTime() / 1000);
}

/** Constant-time password check: compares fixed-length digests, so length leaks nothing either. */
export function passwordMatches(input: string, expected: string): boolean {
  return timingSafeEqual(digest(input), digest(expected));
}

function sign(secret: string, expiresAt: number): string {
  return createHmac("sha256", secret).update(`v1.${expiresAt}`).digest("base64url");
}

function digest(value: string): Buffer {
  return createHash("sha256").update(value, "utf8").digest();
}

function safeEqual(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}

/**
 * A 303 to a same-origin path. Relative on purpose: behind Docker/proxies `request.url` carries the
 * server's bind address (e.g. 0.0.0.0:3000), not the host the browser used.
 */
export function seeOther(path: string): ResponseInit {
  return { status: 303, headers: { Location: path, "Cache-Control": "no-store" } };
}

/** Only same-origin relative paths are valid post-login targets (no `//host` or `/\host`). */
export function safeNextPath(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  if (next.startsWith("/login") || next.startsWith("/api/")) return "/";
  return next;
}
