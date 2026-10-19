import "server-only";

import { redirect } from "next/navigation";
import { cache } from "react";

import { sessionToken } from "@/lib/auth";
import type {
  ActivitiesQuery,
  ActivityDetail,
  ActivityPage,
  RangeQuery,
  StatsSummary,
  SyncStatus,
  WeeklyStats,
} from "@/lib/types";
import { toSearchParams } from "@/lib/types";
import { upstreamGet } from "@/lib/upstream";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function rangeQuery(from?: string, to?: string, sportType?: string): RangeQuery {
  return { from, to, sport_type: sportType };
}

/**
 * GET as the signed-in user. A session the API no longer accepts (expired, revoked) sends the
 * browser to the sign-in page instead of rendering an error.
 */
export async function getJson<T>(path: string, query: object = {}): Promise<T> {
  const result = await upstreamGet(path, toSearchParams(query), await sessionToken());
  if (!result.ok && result.status === 401) redirect("/login");
  if (!result.ok) throw new ApiError(result.status, result.error);
  return result.data as T;
}

/**
 * Typed trainsync API client for server components. Same code path as the BFF route, so the
 * session handling lives in one place. `cache` dedupes identical calls within one request.
 */
export const api = {
  activities: (query: ActivitiesQuery = {}) => getJson<ActivityPage>("/v1/activities", query),
  activity: cache((id: number) => getJson<ActivityDetail>(`/v1/activities/${id}`)),
  // Primitive arguments, so `cache` (which compares arguments by identity) can dedupe them.
  weekly: cache((from?: string, to?: string, sportType?: string) =>
    getJson<WeeklyStats>("/v1/stats/weekly", rangeQuery(from, to, sportType)),
  ),
  summary: cache((from?: string, to?: string, sportType?: string) =>
    getJson<StatsSummary>("/v1/stats/summary", rangeQuery(from, to, sportType)),
  ),
  syncStatus: cache(() => getJson<SyncStatus>("/v1/sync/status")),
};

export type Loaded<T> = { ok: true; data: T } | { ok: false; status: number; error: string };

/** Turns an API call into a value a data block can render (data or an error state). */
export async function load<T>(call: () => Promise<T>): Promise<Loaded<T>> {
  try {
    return { ok: true, data: await call() };
  } catch (error) {
    if (error instanceof ApiError) return { ok: false, status: error.status, error: error.message };
    throw error;
  }
}
