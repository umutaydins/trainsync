import type { Activity, ActivityPage, SyncStatus } from "@/lib/types";

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

export function syncStatus(overrides: Partial<SyncStatus> = {}): SyncStatus {
  const run = {
    id: 1,
    status: "succeeded",
    pages: 2,
    upserted: 300,
    error_code: null,
    error: null,
    started_at: "2026-10-18T09:00:00Z",
    updated_at: "2026-10-18T09:01:00Z",
    finished_at: "2026-10-18T09:01:00Z",
  };
  return {
    athletes: [{ athlete_id: 1, strava_athlete_id: 1001, backfill: run, incremental: null }],
    last_synced_at: "2026-10-18T09:01:00Z",
    webhooks: { pending: 0, processing: 0, failed: 2, dead_letters: 1, last_received_at: null, last_processed_at: null },
    rate_limit: { short_ratio: 0.85, daily_ratio: 0.1, window_start: "2026-10-18T09:00:00Z", blocked_until: null },
    circuit: {
      state: "half_open",
      processes: [
        { process: "api", state: "closed", retry_at: null, changed_at: "2026-10-18T09:00:00Z" },
        { process: "worker-1", state: "half_open", retry_at: null, changed_at: "2026-10-18T09:00:00Z" },
      ],
    },
    ...overrides,
  };
}
