import "server-only";

import { cache } from "react";

import { getJson } from "@/lib/api";
import type { DayLog, DaySummary, FoodList, Profile, RangeSummary } from "@/lib/nutrition-types";

/** Typed `/v1/nutrition` reads for server components (same path as the BFF, ADR 0011). */
export const nutritionApi = {
  summary: cache((date?: string) => getJson<DaySummary>("/v1/nutrition/summary", { date })),
  weekly: cache((from?: string, to?: string) => getJson<RangeSummary>("/v1/nutrition/summary/weekly", { from, to })),
  log: cache((date?: string) => getJson<DayLog>("/v1/nutrition/log", { date })),
  favorites: cache(() => getJson<FoodList>("/v1/nutrition/foods", { favorites: true, limit: 50 })),
  profile: cache(() => getJson<Profile>("/v1/nutrition/profile")),
};
