import type { KeyValueStore } from "@/lib/timers";
import type { Exercise, PlannedExercise, PlatesOut, ProgramPreview, WorkoutDetail } from "@/lib/training-types";

export function exercise(id: number, overrides: Partial<Exercise> = {}): Exercise {
  return {
    id,
    slug: `exercise-${id}`,
    name: `Exercise ${id}`,
    primary_muscle: "chest",
    secondary_muscles: [],
    equipment: "barbell",
    movement_pattern: "horizontal_push",
    is_custom: false,
    ...overrides,
  };
}

export const BENCH = exercise(20, { slug: "bench-press", name: "Bench Press" });
export const CURL = exercise(31, { slug: "dumbbell-curl", name: "Dumbbell Curl", primary_muscle: "biceps", equipment: "dumbbell" });

export function planned(ex: Exercise, overrides: Partial<PlannedExercise> = {}): PlannedExercise {
  return {
    exercise: ex,
    sets: 3,
    rep_min: 8,
    rep_max: 12,
    rest_seconds: 90,
    start_weight_kg: 60,
    progression: "double",
    last_performance: {
      workout_id: 41,
      started_at: "2026-10-15T17:30:00Z",
      sets: [
        { reps: 12, weight_kg: 77.5, rpe: null },
        { reps: 12, weight_kg: 77.5, rpe: null },
        { reps: 12, weight_kg: 77.5, rpe: null },
      ],
    },
    suggestion: { action: "increase", weight_kg: 80, previous_weight_kg: 77.5 },
    ...overrides,
  };
}

export function workout(overrides: Partial<WorkoutDetail> = {}): WorkoutDetail {
  return {
    id: 42,
    client_id: "2d7f6c0a-5b1e-4c3a-8f0e-9a4b1c2d3e4f",
    program_day_id: 11,
    program_day_name: "Upper A",
    started_at: "2026-10-18T17:30:00Z",
    ended_at: null,
    notes: "",
    set_count: 0,
    exercise_count: 0,
    volume_kg: 0,
    planned: [planned(BENCH), planned(CURL, { sets: 2, rest_seconds: 60, suggestion: { action: "hold", weight_kg: 12.5, previous_weight_kg: 12.5 }, last_performance: null })],
    sets: [],
    records: [],
    ...overrides,
  };
}

export const PLATES_100: PlatesOut = {
  target_kg: 101,
  bar_kg: 20,
  per_side: [25, 15],
  achieved_kg: 100,
  difference_kg: 1,
  exact: false,
};

export const PLATES_MIXED: PlatesOut = {
  target_kg: 87.5,
  bar_kg: 20,
  per_side: [20, 10, 2.5, 1.25],
  achieved_kg: 87.5,
  difference_kg: 0,
  exact: true,
};

export const PREVIEW: ProgramPreview = {
  template: "upper_lower",
  days: [
    { name: "Upper A", estimated_minutes: 52.5, exercises: [{ exercise_id: 20, slug: "bench-press", name: "Bench Press", role: "compound" }, { exercise_id: 31, slug: "dumbbell-curl", name: "Dumbbell Curl", role: "accessory" }] },
    { name: "Lower A", estimated_minutes: 48, exercises: [{ exercise_id: 1, slug: "back-squat", name: "Back Squat", role: "compound" }] },
  ],
  program: {
    name: "Upper/Lower hypertrophy",
    goal: "hypertrophy",
    weeks: 8,
    days: [
      {
        name: "Upper A",
        exercises: [
          { exercise_id: 20, sets: 4, rep_min: 8, rep_max: 12, rest_seconds: 90, start_weight_kg: null, progression: "double" },
          { exercise_id: 31, sets: 3, rep_min: 10, rep_max: 15, rest_seconds: 60, start_weight_kg: null, progression: "double" },
        ],
      },
      { name: "Lower A", exercises: [{ exercise_id: 1, sets: 4, rep_min: 8, rep_max: 12, rest_seconds: 90, start_weight_kg: null, progression: "double" }] },
    ],
  },
};

/** An in-memory localStorage. */
export function memoryStore(): KeyValueStore & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, String(v)),
    removeItem: (k) => void data.delete(k),
  };
}

/** Sequential predictable UUIDs. */
export function idSequence(prefix = "00000000-0000-4000-8000-"): () => string {
  let n = 0;
  return () => `${prefix}${String(++n).padStart(12, "0")}`;
}
