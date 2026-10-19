import type { MutationResult } from "@/lib/mutate";
import { toSearchParams } from "@/lib/types";

/**
 * Browser-side read through the BFF (`GET /api/ts/<path>`), with the same never-throwing result
 * shape as `mutate`. `path` is the API path, e.g. `/v1/training/plates`.
 */
export async function bffGet<T>(
  path: string,
  query: object = {},
  options: { signal?: AbortSignal; fetchImpl?: typeof fetch } = {},
): Promise<MutationResult<T>> {
  if (!path.startsWith("/v1/")) throw new Error(`bffGet: path must start with /v1/, got ${path}`);
  const search = toSearchParams(query).toString();
  let response: Response;
  try {
    response = await (options.fetchImpl ?? fetch)(`/api/ts${path}${search ? `?${search}` : ""}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      credentials: "same-origin",
      signal: options.signal,
    });
  } catch {
    return { ok: false, status: 0, error: "network error" };
  }
  const data: unknown = await response.json().catch(() => null);
  if (response.ok) return { ok: true, status: response.status, data: data as T };
  const error = (data as { error?: unknown } | null)?.error;
  return { ok: false, status: response.status, error: typeof error === "string" ? error : `request failed (${response.status})` };
}
