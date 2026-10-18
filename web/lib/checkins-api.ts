import "server-only";

import { cache } from "react";

import { ApiError } from "@/lib/api";
import type { Checkin, CheckinList, CheckinSummary } from "@/lib/checkins";
import { toSearchParams } from "@/lib/types";
import { upstreamGet } from "@/lib/upstream";

async function getJson<T>(path: string, query: object = {}): Promise<T> {
  const result = await upstreamGet(path, toSearchParams(query));
  if (!result.ok) throw new ApiError(result.status, result.error);
  return result.data as T;
}

/** Server-side reads of `/v1/checkins` (P6.9); writes go through the BFF from the browser. */
export const checkinsApi = {
  list: cache((from?: string, to?: string) => getJson<CheckinList>("/v1/checkins", { from, to })),
  summary: cache((from?: string, to?: string) => getJson<CheckinSummary>("/v1/checkins/summary", { from, to })),
  /** The day's check-in, or null when there is none (404). */
  day: cache(async (day: string): Promise<Checkin | null> => {
    try {
      return await getJson<Checkin>(`/v1/checkins/${day}`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  }),
};
