import type { Change, Heatmap, PersonalRecord, ProgressSummary, Records, Series } from "@/features/progress/types";
import type { ProgramOut } from "@/features/training/types";
import { exercise } from "./training-fixtures";

type ProgramDay = ProgramOut["days"][number];
import type { ActivityPage } from "@/lib/types";

/** Progress fixtures, typed from the generated schemas (values from docs/openapi.json's examples). */

export function change(value: number | null, previous: number | null): Change {
  const diff = value != null && previous != null ? value - previous : null;
  return { value, previous, change: diff, change_pct: diff != null && previous ? (diff / previous) * 100 : null };
}

const ZERO = change(0, null);

export function progressSummary(overrides: Partial<ProgressSummary> = {}): ProgressSummary {
  return {
    period: "month",
    timezone: "Europe/Berlin",
    window: { from: "2026-10-01", to: "2026-10-19", days: 19 },
    previous: { from: "2026-09-01", to: "2026-09-19", days: 19 },
    from: "2026-10-01",
    to: "2026-10-19",
    sport_type: null,
    totals: { count: 11, distance_m: 98_400, moving_time_s: 31_200, elevation_gain_m: 640 },
    by_sport: [{ sport_type: "Run", count: 11, distance_m: 98_400, moving_time_s: 31_200, elevation_gain_m: 640 }],
    longest: null,
    last_synced_at: "2026-10-18T09:30:02Z",
    endurance: {
      totals: {
        count: change(11, 9),
        distance_m: change(98_400, 83_640),
        moving_time_s: change(31_200, 28_080),
        elevation_gain_m: change(640, 768),
        average_speed_mps: change(3.15, 2.95),
        average_heartrate: change(148.2, 151),
      },
      by_group: [
        {
          group: "run",
          count: change(9, 7),
          distance_m: change(86_400, 73_440),
          moving_time_s: change(27_600, 24_840),
          elevation_gain_m: change(560, 672),
          average_speed_mps: change(3.125, 2.95),
          average_heartrate: change(148.2, 151),
        },
        {
          group: "ride",
          count: change(2, 2),
          distance_m: change(12_000, 10_200),
          moving_time_s: change(3600, 3240),
          elevation_gain_m: change(80, 96),
          average_speed_mps: change(8, 7.5),
          average_heartrate: change(null, null),
        },
      ],
      longest: [],
      fastest: [],
    },
    strength: {
      sessions: change(6, 5),
      sets: change(102, 90),
      reps: change(820, 700),
      tonnage_kg: change(41_200, 36_000),
      pr_count: change(2, 1),
      by_muscle: [
        { muscle: "chest", sets: 24, tonnage_kg: 11_400 },
        { muscle: "back", sets: 30, tonnage_kg: 12_000 },
      ],
      by_exercise: [
        { exercise_id: 1, name: "Bench Press", muscle: "chest", sets: 15, reps: 90, tonnage_kg: 7650, best_e1rm_kg: change(101.67, 98) },
      ],
      adherence: {
        program_id: 3,
        program_name: "Upper/Lower 4-day",
        planned_sessions: 8,
        done_sessions: 6,
        planned_sets: 136,
        done_sets: 102,
        session_ratio: 0.75,
        set_ratio: 0.75,
      },
    },
    consistency: {
      active_days: change(14, 12),
      training_streak_weeks: 9,
      longest_training_streak_weeks: 15,
      checkin_streak_days: 6,
      longest_checkin_streak_days: 41,
      checkin_rate: change(0.89, 0.79),
      sick_days: 0,
    },
    nutrition: {
      logged_days: change(17, 15),
      logging_rate: change(0.89, 0.79),
      avg_kcal: change(2480, 2610),
      kcal_target: 2500,
      avg_protein_g: change(152, 139),
      avg_carbs_g: change(270, 301),
      avg_fat_g: change(81, 86),
      days_over_sugar_limit: change(2, 5),
      sugar_limit_g: 50,
    },
    body: {
      first_kg: 81.4,
      last_kg: 80.6,
      change_kg: change(-0.8, -0.3),
      moving_average_kg: 80.8,
      rate_kg_per_week: change(-0.31, -0.12),
      body_fat_pct: null,
    },
    ...overrides,
  };
}

/** `all`: no previous period, so no change anywhere. */
export function allTimeSummary(): ProgressSummary {
  const s = progressSummary({ period: "all", previous: null });
  const strip = (c: Change): Change => ({ value: c.value, previous: null, change: null, change_pct: null });
  return {
    ...s,
    endurance: { ...s.endurance, totals: { ...s.endurance.totals, distance_m: strip(s.endurance.totals.distance_m), count: strip(s.endurance.totals.count) } },
  };
}

/** A fresh account: zeros and nulls everywhere. */
export function emptySummary(): ProgressSummary {
  const s = progressSummary();
  return {
    ...s,
    totals: { count: 0, distance_m: 0, moving_time_s: 0, elevation_gain_m: 0 },
    by_sport: [],
    last_synced_at: null,
    endurance: {
      totals: { count: ZERO, distance_m: ZERO, moving_time_s: ZERO, elevation_gain_m: ZERO, average_speed_mps: change(null, null), average_heartrate: change(null, null) },
      by_group: [],
      longest: [],
      fastest: [],
    },
    strength: { sessions: ZERO, sets: ZERO, reps: ZERO, tonnage_kg: ZERO, pr_count: ZERO, by_muscle: [], by_exercise: [], adherence: null },
    consistency: { ...s.consistency, active_days: ZERO, training_streak_weeks: 0, checkin_streak_days: 0, checkin_rate: ZERO },
    nutrition: { ...s.nutrition, logged_days: ZERO, avg_kcal: change(null, null) },
    body: { first_kg: null, last_kg: null, change_kg: change(null, null), moving_average_kg: null, rate_kg_per_week: change(null, null), body_fat_pct: null },
  };
}

export function series(metric: Series["metric"], values: (number | null)[], overrides: Partial<Series> = {}): Series {
  return {
    metric,
    period: "month",
    bucket: "day",
    timezone: "Europe/Berlin",
    window: { from: "2026-10-01", to: "2026-10-19", days: 19 },
    sport: null,
    target: null,
    points: values.map((value, i) => ({ start: `2026-10-${String(i + 1).padStart(2, "0")}`, value, moving_average: null })),
    ...overrides,
  };
}

export function weightSeries(): Series {
  const s = series("weight_kg", [81.4, null, 81.1, 80.9, null, 80.6]);
  return { ...s, points: s.points.map((p, i) => ({ ...p, moving_average: i === 0 ? null : 81 - i * 0.05 })) };
}

export function heatmap(year = 2026, active: Record<string, number> = { "2026-10-12": 64.5, "2026-10-19": 182 }): Heatmap {
  const days: Heatmap["days"] = [];
  for (let d = new Date(Date.UTC(year, 0, 1)); d.getUTCFullYear() === year; d.setUTCDate(d.getUTCDate() + 1)) {
    const day = d.toISOString().slice(0, 10);
    const value = active[day] ?? 0;
    days.push({ day, value, sessions: value > 0 ? 1 : 0, checkin: value > 0 ? "done" : null });
  }
  const max = Math.max(0, ...Object.values(active));
  return { year, timezone: "Europe/Berlin", max_value: max, days };
}

export function record(overrides: Partial<PersonalRecord> = {}): PersonalRecord {
  return { exercise_id: 1, name: "Bench Press", workout_id: 418, achieved_at: "2026-10-16T17:40:02Z", e1rm_kg: 101.67, previous_kg: 100, ...overrides };
}

export function records(items: PersonalRecord[], overrides: Partial<Records> = {}): Records {
  return { period: "all", window: { from: "2024-03-02", to: "2026-10-19", days: 962 }, count: items.length, records: items, ...overrides };
}

export const ALL_RECORDS = [
  record(),
  record({ exercise_id: 2, name: "Squat", workout_id: 400, achieved_at: "2026-09-30T17:00:00Z", e1rm_kg: 140, previous_kg: 135 }),
  record({ workout_id: 300, achieved_at: "2026-08-01T17:00:00Z", e1rm_kg: 100, previous_kg: null }),
];

export function program(overrides: Partial<ProgramOut> = {}): ProgramOut {
  const planned = (id: number, name: string): ProgramDay["exercises"][number] => ({
    id,
    exercise: exercise(id, { name }),
    position: id,
    sets: 3,
    rep_min: 6,
    rep_max: 10,
    rest_seconds: 120,
    start_weight_kg: null,
    progression: "double",
  });
  return {
    id: 3,
    name: "Upper/Lower 4-day",
    goal: "hypertrophy",
    days_per_week: 4,
    weeks: 8,
    active: true,
    created_at: "2026-09-01T08:00:00Z",
    days: [
      { id: 11, day_index: 0, name: "Upper A", weekday: 0, start_time: null, exercises: [planned(1, "Bench Press"), planned(2, "Row")] },
      { id: 12, day_index: 1, name: "Lower A", weekday: 2, start_time: null, exercises: [planned(3, "Squat")] },
    ],
    ...overrides,
  };
}

export function activities(count: 0 | 1): ActivityPage {
  return {
    items: count
      ? [
          {
            id: 812,
            athlete_id: 1,
            name: "Long run",
            sport_type: "Run",
            start_date: "2026-10-18T07:02:11Z",
            distance_m: 21_300,
            moving_time_s: 6840,
            elapsed_time_s: 7000,
            elevation_gain_m: 120,
            average_heartrate: 150,
            synced_at: "2026-10-18T09:30:02Z",
          },
        ]
      : [],
    next_cursor: null,
    last_synced_at: count ? "2026-10-19T09:30:00Z" : null,
  };
}
