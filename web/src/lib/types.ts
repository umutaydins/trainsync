import type { components, paths } from "@/lib/api-types";

type Schemas = components["schemas"];

export type Activity = Schemas["ActivityOut"];
export type ActivityPage = Schemas["ActivityPage"];
export type ActivityDetail = Schemas["ActivityDetail"];
export type WeeklyStats = Schemas["WeeklyStats"];
export type Week = Schemas["Week"];
/** The activity fields of `/v1/stats/summary` the current pages read (the progress blocks of
 * P8.10 are typed where they are shown). */
export type StatsSummary = Pick<
  Schemas["StatsSummary"],
  "from" | "to" | "sport_type" | "totals" | "by_sport" | "longest" | "last_synced_at"
>;
export type SportTotals = Schemas["SportTotalsOut"];
export type SyncStatus = Schemas["SyncStatusOut"];
export type SyncRun = Schemas["RunOut"];
export type BreakerState = Schemas["BreakerState"];

type QueryOf<P extends keyof paths> = paths[P] extends { get: { parameters: { query?: infer Q } } }
  ? NonNullable<Q>
  : never;

export type ActivitiesQuery = QueryOf<"/v1/activities">;
export type RangeQuery = QueryOf<"/v1/stats/summary">;

/** `{error}` body of every failed BFF response. */
export interface ErrorBody {
  error: string;
}

export function toSearchParams(query: object = {}): URLSearchParams {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  return search;
}
