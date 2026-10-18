import "server-only";

import { serverEnv } from "@/lib/env";

/** The only API paths the web app may read. Everything else is rejected before any fetch. */
const ALLOWED_PATHS: readonly RegExp[] = [
  /^\/v1\/activities$/,
  /^\/v1\/activities\/\d{1,20}$/,
  /^\/v1\/stats\/weekly$/,
  /^\/v1\/stats\/summary$/,
  /^\/v1\/sync\/status$/,
];

const TIMEOUT_MS = 10_000;

export function isAllowedPath(path: string): boolean {
  return ALLOWED_PATHS.some((pattern) => pattern.test(path));
}

export type UpstreamResult =
  | { ok: true; status: number; data: unknown }
  | { ok: false; status: number; error: string };

type Fetch = typeof fetch;

/**
 * GET an allowlisted API path with the server-side API key. Shared by the BFF route handler
 * (browser → /api/ts/...) and by server components (lib/api.ts).
 */
export async function upstreamGet(
  path: string,
  search: URLSearchParams = new URLSearchParams(),
  fetchImpl: Fetch = fetch,
): Promise<UpstreamResult> {
  if (!isAllowedPath(path)) return { ok: false, status: 404, error: "not found" };
  const env = serverEnv();
  const url = new URL(`${env.apiUrl}${path}`);
  url.search = search.toString();

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers: { "X-API-Key": env.apiKey, Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    return { ok: false, status: 502, error: "trainsync API unavailable" };
  }

  const body: unknown = await response.json().catch(() => null);
  if (response.ok) return { ok: true, status: response.status, data: body };
  return { ok: false, status: response.status, error: errorMessage(response.status, body) };
}

function errorMessage(status: number, body: unknown): string {
  if (status === 401 || status === 403) return "the web app is not authorized for the trainsync API";
  if (body && typeof body === "object" && "detail" in body) {
    const { detail } = body as { detail: unknown };
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return "invalid request parameters";
  }
  return `trainsync API error (${status})`;
}
