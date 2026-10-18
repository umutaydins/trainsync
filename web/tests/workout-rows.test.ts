import { describe, expect, it } from "vitest";

import type { WorkoutLocalState } from "@/lib/timers";
import { buildRows, defaults, groupRows, loggedVolume, parseSet } from "@/lib/workout-rows";
import { BENCH, CURL, idSequence, planned, workout } from "./support/training-fixtures";

describe("workout rows", () => {
  it("makes one row per planned set with fresh client ids", () => {
    const rows = buildRows(workout(), null, idSequence());
    expect(rows.map((r) => [r.exerciseId, r.setIndex, r.status])).toEqual([
      [20, 1, "idle"],
      [20, 2, "idle"],
      [20, 3, "idle"],
      [31, 1, "idle"],
      [31, 2, "idle"],
    ]);
    expect(new Set(rows.map((r) => r.clientId)).size).toBe(5);
  });

  it("keeps saved client ids and marks what the API has as saved", () => {
    const first = buildRows(workout(), null, idSequence());
    const saved: WorkoutLocalState = {
      version: 1,
      workoutId: 42,
      rest: null,
      rows: first.map((r, i) => (i === 0 ? { ...r, status: "saving" } : i === 1 ? { ...r, status: "queued" } : r)),
      extraExercises: [],
    };
    const detail = workout({
      sets: [
        { client_id: first[0]!.clientId, workout_id: 42, exercise_id: 20, set_index: 1, reps: 9, weight_kg: 80, rpe: null, is_warmup: false, completed_at: "2026-10-18T17:40:00Z", rest_seconds: 90 },
        // Logged elsewhere (the bot): becomes a row of its own.
        { client_id: "bot-set", workout_id: 42, exercise_id: 99, set_index: 1, reps: 5, weight_kg: 100, rpe: null, is_warmup: false, completed_at: "2026-10-18T17:41:00Z", rest_seconds: null },
      ],
    });
    const rows = buildRows(detail, saved, idSequence("new-"));
    expect(rows.map((r) => r.clientId)).toEqual([...first.map((r) => r.clientId), "bot-set"]);
    expect(rows[0]).toMatchObject({ status: "saved", reps: "9", weightKg: "80" });
    expect(rows[1]!.status).toBe("queued");
    const groups = groupRows(detail, rows, [], new Map([[BENCH.id, BENCH], [CURL.id, CURL]]));
    expect(groups.map((g) => g.name)).toEqual(["Bench Press", "Dumbbell Curl", "Exercise 99"]);
    expect(loggedVolume(rows)).toBe(9 * 80 + 5 * 100);
  });

  it("a set in flight when the page went away is tappable again with the same id", () => {
    const first = buildRows(workout(), null, idSequence());
    const saved: WorkoutLocalState = { version: 1, workoutId: 42, rest: null, rows: first.map((r) => ({ ...r, status: "saving", completedAt: "2026-10-18T17:40:00Z" })), extraExercises: [] };
    const rows = buildRows(workout(), saved, idSequence("new-"));
    expect(rows[0]).toMatchObject({ clientId: first[0]!.clientId, status: "idle", completedAt: "2026-10-18T17:40:00Z" });
  });

  it("prefills from the suggestion, else last time, else the start weight", () => {
    expect(defaults(planned(BENCH), 1)).toEqual({ reps: "8", weightKg: "80" });
    const hold = planned(BENCH, { suggestion: { action: "hold", weight_kg: 77.5, previous_weight_kg: 77.5 } });
    expect(defaults({ ...hold, last_performance: { workout_id: 1, started_at: "x", sets: [{ reps: 9, weight_kg: 77.5, rpe: null }] } }, 1)).toEqual({ reps: "10", weightKg: "77.5" });
    expect(defaults(planned(BENCH, { suggestion: { action: "start", weight_kg: null, previous_weight_kg: null }, last_performance: null, start_weight_kg: null }), 1)).toEqual({ reps: "8", weightKg: "" });
  });

  it("parses reps and kg like the API validates them", () => {
    expect(parseSet("8", "80")).toEqual({ ok: true, reps: 8, weightKg: 80 });
    expect(parseSet("8", "")).toEqual({ ok: true, reps: 8, weightKg: 0 });
    expect(parseSet("8", "2,25")).toEqual({ ok: true, reps: 8, weightKg: 2.25 });
    expect(parseSet("", "80").ok).toBe(false);
    expect(parseSet("8.5", "80").ok).toBe(false);
    expect(parseSet("101", "80").ok).toBe(false);
    expect(parseSet("8", "80.1").ok).toBe(false);
    expect(parseSet("8", "501").ok).toBe(false);
  });
});
