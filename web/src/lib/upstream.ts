import "server-only";

import { BACKEND_UNREACHABLE_TEXT } from "@/lib/backend-copy";
import { serverEnv } from "@/lib/env";

export type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export type MutationMethod = "POST" | "PUT" | "PATCH" | "DELETE";

/** Shown when the API cannot be reached at all (network error or timeout). */
export const BACKEND_UNREACHABLE = BACKEND_UNREACHABLE_TEXT;

const READ: readonly Method[] = ["GET"];
const READ_WRITE: readonly Method[] = ["GET", "POST", "PUT", "DELETE"];
const READ_WRITE_PATCH: readonly Method[] = [...READ_WRITE, "PATCH"];
const READ_PATCH: readonly Method[] = ["GET", "PATCH"];
const READ_DELETE: readonly Method[] = ["GET", "DELETE"];
const POST_ONLY: readonly Method[] = ["POST"];
const DELETE_ONLY: readonly Method[] = ["DELETE"];

/** Shown when the API refuses the session (expired, revoked, signed out elsewhere). */
export const NOT_SIGNED_IN = "not signed in";

/**
 * The only API paths and methods the web app may use (ADR 0011). A path that matches no rule is
 * 404, a path that matches with another method is 405. Rules are checked against already
 * validated segments (see `splitPath`), so `**` cannot be escaped with `..` or encoded slashes.
 */
export const RULES: readonly { pattern: RegExp; methods: readonly Method[] }[] = [
  { pattern: /^\/v1\/activities$/, methods: READ },
  { pattern: /^\/v1\/activities\/\d{1,20}$/, methods: READ },
  { pattern: /^\/v1\/stats\/weekly$/, methods: READ },
  { pattern: /^\/v1\/stats\/summary$/, methods: READ },
  { pattern: /^\/v1\/sync\/status$/, methods: READ },
  // The account (P8.1-P8.6). The web app deletes it and signs out through its own route
  // handlers, which also end the browser session.
  { pattern: /^\/v1\/me$/, methods: [...READ_PATCH, "DELETE"] },
  { pattern: /^\/v1\/me\/strava\/authorize-url$/, methods: POST_ONLY },
  { pattern: /^\/v1\/me\/settings$/, methods: READ_PATCH },
  { pattern: /^\/v1\/me\/password$/, methods: POST_ONLY },
  { pattern: /^\/v1\/me\/sessions$/, methods: READ },
  { pattern: /^\/v1\/me\/sessions\/\d{1,20}$/, methods: DELETE_ONLY },
  { pattern: /^\/v1\/me\/(?:telegram|strava)$/, methods: READ_DELETE },
  { pattern: /^\/v1\/me\/telegram\/code$/, methods: POST_ONLY },
  { pattern: /^\/v1\/me\/export$/, methods: READ },
  // Owner only; the API answers 403 to everyone else.
  { pattern: /^\/v1\/admin\/(?:invites|users)$/, methods: ["GET", "POST"] },
  { pattern: /^\/v1\/admin\/invites\/\d{1,20}$/, methods: DELETE_ONLY },
  { pattern: /^\/v1\/admin\/users\/\d{1,20}\/reset-link$/, methods: POST_ONLY },
  // Partial updates of a food (P6.4) or a custom exercise (P6.2) are the only PATCHes; the first
  // matching rule wins.
  { pattern: /^\/v1\/nutrition\/foods\/\d{1,20}$/, methods: READ_WRITE_PATCH },
  { pattern: /^\/v1\/training\/exercises\/\d{1,20}$/, methods: READ_WRITE_PATCH },
  // `/v1/training/**`, `/v1/nutrition/**`, `/v1/checkins/**` (the roots included).
  { pattern: /^\/v1\/(?:training|nutrition|checkins)(?:\/[^/]+)*$/, methods: READ_WRITE },
];

/**
 * One path segment: ids, UUIDs, dates, slugs. No leading dot (so no `.`/`..`), no `/`, `\`, `%`,
 * whitespace or other characters a URL parser could reinterpret.
 */
const SEGMENT = /^[A-Za-z0-9_~-][A-Za-z0-9_.~-]{0,127}$/;
const MAX_SEGMENTS = 16;

/**
 * Per-request budget for the API call. Below Vercel's default function limit (P7.6), so a Mac
 * that is asleep or offline gives a friendly "backend unreachable" answer, not a platform timeout.
 */
export const DEFAULT_TIMEOUT_MS = 8_000;

function timeoutMs(): number {
  const value = Number(process.env.UPSTREAM_TIMEOUT_MS);
  return Number.isFinite(value) && value > 0 ? value : DEFAULT_TIMEOUT_MS;
}

/** Largest mutation body the BFF forwards to the API. */
export const MAX_BODY_BYTES = 64 * 1024;

/** `/a/b` → `["a", "b"]`, or null if any segment is unsafe. */
function splitPath(path: string): string[] | null {
  if (!path.startsWith("/")) return null;
  const segments = path.slice(1).split("/");
  if (segments.length > MAX_SEGMENTS) return null;
  return segments.every((segment) => SEGMENT.test(segment)) ? segments : null;
}

/** Methods allowed on `path`, or null when the path is not allowlisted at all. */
export function allowedMethods(path: string): readonly Method[] | null {
  if (!splitPath(path)) return null;
  return RULES.find((rule) => rule.pattern.test(path))?.methods ?? null;
}

export function isAllowed(method: Method, path: string): boolean {
  return allowedMethods(path)?.includes(method) ?? false;
}

export function isAllowedPath(path: string): boolean {
  return isAllowed("GET", path);
}

const DEMO_HEADER = "x-trainsync-demo";
export const DEMO_READ_ONLY = "This is a read-only demo.";

export type UpstreamResult =
  | { ok: true; status: number; data: unknown }
  | { ok: false; status: number; error: string; detail?: unknown; retryAfter?: string | null };

type Fetch = typeof fetch;

/**
 * GET an allowlisted API path as the signed-in user. Shared by the BFF route handler
 * (browser → /api/ts/...) and by server components (lib/api.ts).
 */
export function upstreamGet(
  path: string,
  search: URLSearchParams,
  token: string | null,
  fetchImpl: Fetch = fetch,
): Promise<UpstreamResult> {
  return upstreamRequest("GET", path, search, null, token, fetchImpl);
}

/**
 * Send an allowlisted request as the signed-in user (`Authorization: Bearer <token>`; the shared
 * API key never serves a user request, ADR 0034). `body` is already validated JSON text (or
 * null). Only the status and the JSON body of the answer are used; upstream headers are never
 * passed on.
 */
export async function upstreamRequest(
  method: Method,
  path: string,
  search: URLSearchParams,
  body: string | null,
  token: string | null,
  fetchImpl: Fetch = fetch,
): Promise<UpstreamResult> {
  if (!isAllowed(method, path)) return { ok: false, status: 404, error: "not found" };
  if (!token) return { ok: false, status: 401, error: NOT_SIGNED_IN };
  return send(method, path, search, body, { Authorization: `Bearer ${token}` }, fetchImpl);
}

/** The sign-in routes of the API (`/v1/auth/*`): no session yet, so no credentials. */
export function authRequest(
  method: Method,
  path: `/v1/auth/${string}`,
  body: string | null,
  headers: Record<string, string> = {},
  fetchImpl: Fetch = fetch,
): Promise<UpstreamResult> {
  return send(method, path, new URLSearchParams(), body, headers, fetchImpl);
}

async function send(
  method: Method,
  path: string,
  search: URLSearchParams,
  body: string | null,
  auth: Record<string, string>,
  fetchImpl: Fetch,
): Promise<UpstreamResult> {
  const env = serverEnv();
  const url = new URL(`${env.apiUrl}${path}`);
  url.search = search.toString();

  const headers: Record<string, string> = { ...auth, Accept: "application/json" };
  if (body !== null) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs()),
    });
  } catch {
    return { ok: false, status: 502, error: BACKEND_UNREACHABLE };
  }

  const data: unknown = await response.json().catch(() => null);
  if (response.ok) return { ok: true, status: response.status, data };
  // The public read-only demo (P7.9) refuses writes with a 403 marked by this header; say so
  // instead of reporting an authorization problem.
  if (response.status === 403 && response.headers.get(DEMO_HEADER) === "read-only") {
    return { ok: false, status: 403, error: DEMO_READ_ONLY };
  }
  if (response.status === 429) {
    return { ok: false, status: 429, error: errorMessage(429, data), retryAfter: response.headers.get("retry-after") };
  }
  const error = errorMessage(response.status, data);
  // Field-level details (409 conflicts, 422 validation) help forms; auth failures stay opaque.
  if (!isAuthFailure(response.status) && data && typeof data === "object" && "detail" in data) {
    return { ok: false, status: response.status, error, detail: (data as { detail: unknown }).detail };
  }
  return { ok: false, status: response.status, error };
}

function isAuthFailure(status: number): boolean {
  return status === 401 || status === 403;
}

function errorMessage(status: number, body: unknown): string {
  if (status === 401) return NOT_SIGNED_IN;
  if (status === 403) return "not allowed";
  if (body && typeof body === "object" && "detail" in body) {
    const { detail } = body as { detail: unknown };
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return "invalid request parameters";
  }
  return `trainsync API error (${status})`;
}
