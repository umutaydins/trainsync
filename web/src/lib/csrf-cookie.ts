/**
 * CSRF double-submit names, shared by the server (lib/csrf.ts) and the browser (lib/mutate.ts).
 * Nothing secret lives here: this module ends up in the client bundle.
 */
export const CSRF_COOKIE = "ts_csrf";
export const CSRF_HEADER = "X-CSRF-Token";

/** The CSRF cookie's value from a `document.cookie` string, or null. */
export function readCsrfCookie(cookieHeader: string): string | null {
  for (const part of cookieHeader.split(";")) {
    const index = part.indexOf("=");
    if (index < 0) continue;
    if (part.slice(0, index).trim() === CSRF_COOKIE) {
      const value = part.slice(index + 1).trim();
      return value || null;
    }
  }
  return null;
}
