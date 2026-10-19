import "server-only";

import { serverEnv } from "@/lib/env";

/** Liveness budget: short, so the error page answers quickly when the Mac is asleep. */
export const STATUS_TIMEOUT_MS = 3_000;

/**
 * Whether the trainsync API answers its liveness probe at all (P7.6). Used by the error page to
 * tell "the backend is unreachable" apart from other errors; no API key, no data.
 */
export async function backendReachable(fetchImpl: typeof fetch = fetch): Promise<boolean> {
  try {
    const response = await fetchImpl(`${serverEnv().apiUrl}/health/live`, {
      cache: "no-store",
      signal: AbortSignal.timeout(STATUS_TIMEOUT_MS),
    });
    return response.ok;
  } catch {
    return false;
  }
}
