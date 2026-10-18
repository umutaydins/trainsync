import type { Activity, ActivityPage, StatsSummary, Week } from "@/lib/types";

export function activity(id: number, overrides: Partial<Activity> = {}): Activity {
  return {
    id,
    athlete_id: 1,
    name: `Activity ${id}`,
    sport_type: "Run",
    start_date: "2026-10-01T06:30:00Z",
    distance_m: 10_000,
    moving_time_s: 3000,
    elapsed_time_s: 3100,
    elevation_gain_m: 42,
    average_heartrate: 151.2,
    synced_at: "2026-10-01T07:02:11Z",
    ...overrides,
  };
}

export function page(ids: number[], nextCursor: string | null): ActivityPage {
  return { items: ids.map((id) => activity(id)), next_cursor: nextCursor, last_synced_at: null };
}

export function summary(overrides: Partial<StatsSummary> = {}): StatsSummary {
  return {
    from: "2026-09-07",
    to: "2026-10-04",
    sport_type: null,
    totals: { count: 18, distance_m: 352_295, moving_time_s: 74_600, elevation_gain_m: 2493 },
    by_sport: [
      { sport_type: "Ride", count: 4, distance_m: 205_000, moving_time_s: 24_600, elevation_gain_m: 1850 },
      { sport_type: "Run", count: 11, distance_m: 141_295, moving_time_s: 42_300, elevation_gain_m: 643 },
      { sport_type: "Swim", count: 3, distance_m: 6000, moving_time_s: 7700, elevation_gain_m: 0 },
    ],
    longest: activity(7, { distance_m: 100_000, sport_type: "Ride", name: "Long ride" }),
    last_synced_at: "2026-10-18T09:30:02Z",
    ...overrides,
  };
}

export function week(start: string, count = 1, distance = 10_000): Week {
  return { week_start: start, count, distance_m: distance, moving_time_s: 3600, elevation_gain_m: 50 };
}
