import { CSRF_HEADER, readCsrfCookie } from "@/lib/csrf-cookie";

/**
 * Browser calls of Me that end the browser session, so they go to the web app's own route
 * handlers instead of the BFF proxy (`/api/account`, `/api/auth/logout`).
 */

/** Status 0: no answer (offline). */
export type AccountResult = { ok: true } | { ok: false; status: number };

/** `DELETE /api/account` with the password; the route ends the browser session on success. */
export async function deleteAccount(password: string, fetchImpl: typeof fetch = fetch): Promise<AccountResult> {
  const headers: Record<string, string> = { "Content-Type": "application/json", Accept: "application/json" };
  const token = readCsrfCookie(document.cookie);
  if (token) headers[CSRF_HEADER] = token;
  try {
    const response = await fetchImpl("/api/account", {
      method: "DELETE",
      headers,
      body: JSON.stringify({ password }),
      credentials: "same-origin",
      cache: "no-store",
    });
    return response.ok ? { ok: true } : { ok: false, status: response.status };
  } catch {
    return { ok: false, status: 0 };
  }
}

/** Clears the browser session (best effort: the API session may already be gone). */
export async function signOut(fetchImpl: typeof fetch = fetch): Promise<void> {
  await fetchImpl("/api/auth/logout", { method: "POST", credentials: "same-origin", cache: "no-store" }).catch(
    () => undefined,
  );
}

/** A full page load, so no client cache of the signed-in app survives. */
export function leaveTo(path: string): void {
  window.location.assign(path);
}
