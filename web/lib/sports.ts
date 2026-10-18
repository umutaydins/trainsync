import "server-only";

import { api, load } from "@/lib/api";
import { isoDay } from "@/lib/range";

/** Common Strava sport types, used when the API cannot list the athlete's own. */
const FALLBACK = ["Ride", "Run", "Swim", "Walk", "Hike", "TrailRun", "VirtualRide", "WeightTraining"];
/** Strava was founded in 2009; nothing can start earlier. */
const ALL_TIME_FROM = "2009-01-01";

/** Sport types the athlete actually has (all time), A to Z; plus the selected one. */
export async function sportTypes(selected?: string): Promise<string[]> {
  const result = await load(() => api.summary(ALL_TIME_FROM, isoDay(new Date())));
  const sports = result.ok ? result.data.by_sport.map((s) => s.sport_type) : FALLBACK;
  return [...new Set([...sports, ...(selected ? [selected] : [])])].sort();
}
