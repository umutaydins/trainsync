/**
 * The active-workout screen's set rows: planned sets, sets the API already has, and rows kept in
 * localStorage (with their client ids) merged into one list. Pure, so it is tested without React.
 */

import type { SetDraft, WorkoutLocalState } from "@/features/training/timers";
import type { Exercise, PlannedExercise, SetIn, WorkoutDetail } from "@/features/training/types";

export interface ExerciseGroup {
  exerciseId: number;
  name: string;
  equipment: string;
  restSeconds: number;
  planned: PlannedExercise | null;
  rows: SetDraft[];
}

export type NewId = () => string;

export function newClientId(): string {
  return crypto.randomUUID();
}

function str(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

/** Default reps and weight for set `setIndex` (1-based) of a planned exercise. */
export function defaults(planned: PlannedExercise | null, setIndex: number): { reps: string; weightKg: string } {
  if (!planned) return { reps: "", weightKg: "" };
  const last = planned.last_performance?.sets;
  const lastSet = last?.[setIndex - 1] ?? last?.[last.length - 1];
  const weight = planned.suggestion.weight_kg ?? lastSet?.weight_kg ?? planned.start_weight_kg ?? null;
  let reps = planned.rep_min;
  if (planned.suggestion.action === "hold" && lastSet) {
    reps = Math.min(planned.rep_max, Math.max(planned.rep_min, lastSet.reps + 1));
  }
  return { reps: String(reps), weightKg: str(weight) };
}

function row(exerciseId: number, setIndex: number, planned: PlannedExercise | null, newId: NewId): SetDraft {
  return { clientId: newId(), exerciseId, setIndex, ...defaults(planned, setIndex), completedAt: null, status: "idle" };
}

/**
 * Merges the plan, the API's sets and the saved rows:
 * - a saved row whose client id the API has is `saved` with the API's values;
 * - an API set without a row (logged elsewhere, e.g. the bot) becomes a `saved` row;
 * - every planned exercise gets at least `planned.sets` rows, new ones with fresh client ids.
 * Rows that were `saving` when the page went away are `idle` again (tap to send); `queued` rows
 * stay queued (the retry queue has them).
 */
export function buildRows(detail: WorkoutDetail, saved: WorkoutLocalState | null, newId: NewId): SetDraft[] {
  const server = new Map(detail.sets.map((s) => [s.client_id, s]));
  const rows: SetDraft[] = (saved?.rows ?? []).map((r) => {
    const set = server.get(r.clientId);
    if (set) {
      return { ...r, reps: String(set.reps), weightKg: String(set.weight_kg), completedAt: set.completed_at, status: "saved" as const, error: undefined };
    }
    // Not on the server: an interrupted request (not queued) or a set deleted elsewhere. The row
    // keeps its client id and time, so tapping it again is still idempotent.
    return r.status === "saved" || r.status === "saving" ? { ...r, status: "idle" as const } : r;
  });
  const known = new Set(rows.map((r) => r.clientId));
  for (const set of detail.sets) {
    if (known.has(set.client_id)) continue;
    rows.push({
      clientId: set.client_id,
      exerciseId: set.exercise_id,
      setIndex: set.set_index,
      reps: String(set.reps),
      weightKg: String(set.weight_kg),
      completedAt: set.completed_at,
      status: "saved",
    });
  }
  for (const planned of detail.planned) {
    const id = planned.exercise.id;
    const used = new Set(rows.filter((r) => r.exerciseId === id).map((r) => r.setIndex));
    for (let index = 1; index <= planned.sets; index++) {
      if (!used.has(index)) rows.push(row(id, index, planned, newId));
    }
  }
  return rows;
}

/** Rows grouped by exercise: planned order first, then extra exercises, then anything else. */
export function groupRows(
  detail: WorkoutDetail,
  rows: SetDraft[],
  extras: WorkoutLocalState["extraExercises"],
  exercises: Map<number, Exercise>,
): ExerciseGroup[] {
  const groups: ExerciseGroup[] = [];
  const seen = new Set<number>();
  const add = (exerciseId: number, name: string, equipment: string, restSeconds: number, planned: PlannedExercise | null) => {
    if (seen.has(exerciseId)) return;
    seen.add(exerciseId);
    groups.push({
      exerciseId,
      name,
      equipment,
      restSeconds,
      planned,
      rows: rows.filter((r) => r.exerciseId === exerciseId).sort((a, b) => a.setIndex - b.setIndex),
    });
  };
  for (const p of detail.planned) add(p.exercise.id, p.exercise.name, p.exercise.equipment, p.rest_seconds, p);
  for (const e of extras) add(e.id, e.name, e.equipment, e.restSeconds, null);
  for (const r of rows) {
    const e = exercises.get(r.exerciseId);
    add(r.exerciseId, e?.name ?? `Exercise ${r.exerciseId}`, e?.equipment ?? "", DEFAULT_REST_S, null);
  }
  return groups;
}

export const DEFAULT_REST_S = 90;

/** A new row after the last one of an exercise, prefilled from the previous row. */
export function extraRow(group: ExerciseGroup, newId: NewId): SetDraft {
  const last = group.rows[group.rows.length - 1];
  const setIndex = (last?.setIndex ?? 0) + 1;
  const base = last ? { reps: last.reps, weightKg: last.weightKg } : defaults(group.planned, setIndex);
  return { clientId: newId(), exerciseId: group.exerciseId, setIndex, ...base, completedAt: null, status: "idle" };
}

export type Parsed = { ok: true; reps: number; weightKg: number } | { ok: false; error: string };

/** Reps 0–100 whole; weight 0–500 kg in 0.25 steps (a comma works as the decimal mark). */
export function parseSet(reps: string, weightKg: string): Parsed {
  const r = Number(reps.trim());
  if (reps.trim() === "" || !Number.isInteger(r) || r < 0 || r > 100) return { ok: false, error: "Reps: a whole number from 0 to 100" };
  const w = Number(weightKg.trim().replace(",", ".") || "0");
  if (!Number.isFinite(w) || w < 0 || w > 500 || Math.round(w * 4) !== w * 4) {
    return { ok: false, error: "Weight: 0–500 kg in 0.25 kg steps" };
  }
  return { ok: true, reps: r, weightKg: w };
}

export function setBody(r: SetDraft, parsed: { reps: number; weightKg: number }, completedAt: string, restSeconds: number): SetIn {
  return {
    exercise_id: r.exerciseId,
    set_index: r.setIndex,
    reps: parsed.reps,
    weight_kg: parsed.weightKg,
    is_warmup: false,
    completed_at: completedAt,
    rest_seconds: restSeconds,
  };
}

export function setPath(workoutId: number, clientId: string): string {
  return `/v1/training/workouts/${workoutId}/sets/${clientId}`;
}

/** Volume of the rows the API confirmed (reps × kg), for the live "logged so far" figure. */
export function loggedVolume(rows: SetDraft[]): number {
  return rows
    .filter((r) => r.status === "saved")
    .reduce((sum, r) => {
      const p = parseSet(r.reps, r.weightKg);
      return p.ok ? sum + p.reps * p.weightKg : sum;
    }, 0);
}
