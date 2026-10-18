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

export type UpstreamResult =
  | { ok: true; status: number; data: unknown }
  | { ok: false; status: number; error: string; detail?: unknown };

type Fetch = typeof fetch;

/**
 * GET an allowlisted API path with the server-side API key. Shared by the BFF route handler
 * (browser → /api/ts/...) and by server components (lib/api.ts).
 */
export function upstreamGet(
  path: string,
  search: URLSearchParams = new URLSearchParams(),
  fetchImpl: Fetch = fetch,
): Promise<UpstreamResult> {
  return upstreamRequest("GET", path, search, null, fetchImpl);
}

/**
 * Send an allowlisted request with the server-side API key. `body` is already validated JSON text
 * (or null). Only the status and the JSON body of the answer are used; upstream headers are never
 * passed on.
 */
export async function upstreamRequest(
  method: Method,
  path: string,
  search: URLSearchParams,
  body: string | null,
  fetchImpl: Fetch = fetch,
): Promise<UpstreamResult> {
  if (!isAllowed(method, path)) return { ok: false, status: 404, error: "not found" };
  const env = serverEnv();
  const url = new URL(`${env.apiUrl}${path}`);
  url.search = search.toString();

  const headers: Record<string, string> = { "X-API-Key": env.apiKey, Accept: "application/json" };
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
  if (isAuthFailure(status)) return "the web app is not authorized for the trainsync API";
  if (body && typeof body === "object" && "detail" in body) {
    const { detail } = body as { detail: unknown };
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return "invalid request parameters";
  }
  return `trainsync API error (${status})`;
}
