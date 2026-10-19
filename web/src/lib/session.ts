import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";

/**
 * The browser session (ADR 0034, P8.7): an httpOnly cookie that carries the user's API session
 * token, sealed with AES-256-GCM under a key derived from `DASHBOARD_SESSION_SECRET`. The browser
 * can neither read nor forge it; the BFF opens it and calls the API with `Authorization: Bearer`.
 * The API decides whether the token is still valid (it slides and can be revoked there).
 */
export const SESSION_COOKIE = "ts_session";
/** The API's absolute session cap (SESSION_MAX_AGE_DAYS = 90): the cookie never outlives it. */
export const SESSION_MAX_AGE_S = 90 * 24 * 60 * 60;

const VERSION = "v2";
const IV_BYTES = 12;
const TAG_BYTES = 16;

export interface SessionPayload {
  /** The API session token (opaque). */
  token: string;
  /** Unix seconds; the cookie is refused after it even if the browser still sends it. */
  expiresAt: number;
}

/**
 * Whether cookies get `Secure`: `DASHBOARD_COOKIE_SECURE` if set, otherwise only in production.
 * Here rather than in lib/env.ts because proxy.ts needs it and must not import server-only modules.
 */
export function cookieSecureFromEnv(): boolean {
  const override = process.env.DASHBOARD_COOKIE_SECURE;
  return override ? override === "true" : process.env.NODE_ENV === "production";
}

function key(secret: string): Buffer {
  return createHash("sha256").update(`trainsync-session:${secret}`).digest();
}

/** `v2.<iv>.<ciphertext+tag>` (base64url). */
export function sealSession(payload: SessionPayload, secret: string): string {
  const iv = randomBytes(IV_BYTES);
  const cipher = createCipheriv("aes-256-gcm", key(secret), iv);
  const plain = Buffer.from(JSON.stringify({ t: payload.token, e: payload.expiresAt }), "utf8");
  const sealed = Buffer.concat([cipher.update(plain), cipher.final(), cipher.getAuthTag()]);
  return `${VERSION}.${iv.toString("base64url")}.${sealed.toString("base64url")}`;
}

/** The payload of a well-formed, untampered, unexpired cookie; otherwise null. */
export function openSession(value: string | undefined, secret: string, now: Date): SessionPayload | null {
  if (!value || !secret) return null;
  const [version, ivPart, sealedPart, ...rest] = value.split(".");
  if (version !== VERSION || !ivPart || !sealedPart || rest.length > 0) return null;
  try {
    const iv = Buffer.from(ivPart, "base64url");
    const sealed = Buffer.from(sealedPart, "base64url");
    if (iv.length !== IV_BYTES || sealed.length <= TAG_BYTES) return null;
    const decipher = createDecipheriv("aes-256-gcm", key(secret), iv);
    decipher.setAuthTag(sealed.subarray(sealed.length - TAG_BYTES));
    const plain = Buffer.concat([
      decipher.update(sealed.subarray(0, sealed.length - TAG_BYTES)),
      decipher.final(),
    ]).toString("utf8");
    const data = JSON.parse(plain) as { t?: unknown; e?: unknown };
    if (typeof data.t !== "string" || typeof data.e !== "number") return null;
    if (data.e <= Math.floor(now.getTime() / 1000)) return null;
    return { token: data.t, expiresAt: data.e };
  } catch {
    return null;
  }
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
