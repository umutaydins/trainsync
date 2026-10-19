import { CSRF_HEADER, readCsrfCookie } from "@/lib/csrf-cookie";

/**
 * Browser-side helper for writes through the BFF (ADR 0011): sends JSON to `/api/ts/<path>` with
 * the CSRF double-submit token copied from the `ts_csrf` cookie (set by proxy.ts / login).
 * Never throws for HTTP or network errors; callers branch on `ok`.
 */

export type MutationMethod = "POST" | "PUT" | "PATCH" | "DELETE";

export type MutationResult<T> =
  | { ok: true; status: number; data: T | null }
  | {
      ok: false;
      /** HTTP status, or 0 when the request never got an answer (offline, aborted). */
      status: number;
      error: string;
      /** The API's `detail` (e.g. 422 field errors) when it sent one. */
      detail?: unknown;
    };

export interface MutateOptions {
  signal?: AbortSignal;
  /** Test seams; default to the browser's. */
  fetchImpl?: typeof fetch;
  cookies?: () => string;
}

/** `path` is the API path, e.g. `/v1/training/workouts/42/sets/<uuid>`. */
export async function mutate<T>(
  method: MutationMethod,
  path: string,
  body?: unknown,
  options: MutateOptions = {},
): Promise<MutationResult<T>> {
  if (!path.startsWith("/v1/")) throw new Error(`mutate: path must start with /v1/, got ${path}`);
  const fetchImpl = options.fetchImpl ?? fetch;
  const cookies = options.cookies ?? (() => document.cookie);

  const headers: Record<string, string> = { Accept: "application/json" };
  const token = readCsrfCookie(cookies());
  if (token) headers[CSRF_HEADER] = token;
  const hasBody = body !== undefined;
  if (hasBody || method !== "DELETE") headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetchImpl(`/api/ts${path}`, {
      method,
      headers,
      body: hasBody ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
      cache: "no-store",
      signal: options.signal,
    });
  } catch {
    return { ok: false, status: 0, error: "network error" };
  }

  const data: unknown = response.status === 204 ? null : await response.json().catch(() => null);
  if (response.ok) return { ok: true, status: response.status, data: data as T | null };
  const record = data && typeof data === "object" ? (data as Record<string, unknown>) : {};
  const error = typeof record.error === "string" ? record.error : `request failed (${response.status})`;
  return "detail" in record
    ? { ok: false, status: response.status, error, detail: record.detail }
    : { ok: false, status: response.status, error };
}

export const post = <T>(path: string, body?: unknown, options?: MutateOptions) =>
  mutate<T>("POST", path, body, options);

export const put = <T>(path: string, body?: unknown, options?: MutateOptions) =>
  mutate<T>("PUT", path, body, options);

export const patch = <T>(path: string, body?: unknown, options?: MutateOptions) =>
  mutate<T>("PATCH", path, body, options);

export const del = <T = null>(path: string, options?: MutateOptions) =>
  mutate<T>("DELETE", path, undefined, options);
