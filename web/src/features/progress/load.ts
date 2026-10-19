import "server-only";

import { progressApi } from "@/features/progress/api";
import type { Heatmap, PeriodQuery, ProgressSummary, Records, Series } from "@/features/progress/types";
import { type Loaded, load } from "@/lib/api";

export interface ProgressData {
  query: PeriodQuery;
  /** Today in the user's zone (`YYYY-MM-DD`). */
  today: string;
  summary: Loaded<ProgressSummary>;
  distance: Loaded<Series>;
  tonnage: Loaded<Series>;
  weight: Loaded<Series>;
  kcal: Loaded<Series>;
  heatmap: Loaded<Heatmap>;
  /** Records of the period (the list). */
  prs: Loaded<Records>;
  /** Every record (the e1RM chart, and the first year of data). */
  allPrs: Loaded<Records>;
}

/**
 * Every read of the progress screen, in parallel, each on its own: one failing call is one
 * block's error state, not the page's. Weight and kcal are daily (the moving average and the
 * daily target only exist per day); volume takes the API's default bucket.
 */
export async function loadProgress(query: PeriodQuery, today: string): Promise<ProgressData> {
  const { period, from, to } = query;
  const thisYear = Number(today.slice(0, 4));
  // No year (or one still to come): the last 12 months up to today.
  const year = query.year !== undefined && query.year <= thisYear ? query.year : undefined;
  const [summary, distance, tonnage, weight, kcal, heatmap, prs, allPrs] = await Promise.all([
    load(() => progressApi.summary(period, from, to)),
    load(() => progressApi.series("distance_m", period, from, to)),
    load(() => progressApi.series("tonnage_kg", period, from, to)),
    load(() => progressApi.series("weight_kg", period, from, to, "day")),
    load(() => progressApi.series("kcal", period, from, to, "day")),
    load(() => progressApi.heatmap(year)),
    load(() => progressApi.prs(period, from, to)),
    load(() => progressApi.prs("all")),
  ]);
  return { query, today, summary, distance, tonnage, weight, kcal, heatmap, prs, allPrs };
}

/**
 * Nothing to show at all: an empty period, no record ever and no training this year (a fresh
 * account). The page then shows one "nothing yet" card with the ways to start.
 */
export function isFresh(data: ProgressData): boolean {
  if (!data.summary.ok || !data.allPrs.ok || !data.heatmap.ok) return false;
  const s = data.summary.data;
  return (
    (s.endurance.totals.count.value ?? 0) === 0 &&
    (s.strength.sessions.value ?? 0) === 0 &&
    (s.nutrition.logged_days.value ?? 0) === 0 &&
    s.body.last_kg == null &&
    data.allPrs.data.count === 0 &&
    data.heatmap.data.max_value === 0
  );
}
