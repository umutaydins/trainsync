/**
 * The program editor's working copy: a generated preview or a saved program, edited in place and
 * turned back into the one `ProgramIn` body that `POST`/`PUT /v1/training/programs` validate.
 * Numbers stay strings while typing; `toProgramIn` checks them.
 */

import type { Exercise, ProgramGoal, ProgramIn, ProgramOut, ProgramPreview } from "@/features/training/types";

export interface DraftExercise {
  key: string;
  exerciseId: number;
  name: string;
  equipment: string;
  sets: string;
  repMin: string;
  repMax: string;
  restSeconds: string;
  startWeightKg: string;
  progression: "double" | "none";
}

export interface DraftDay {
  key: string;
  name: string;
  exercises: DraftExercise[];
}

export interface DraftProgram {
  /** Set when editing a saved program (PUT); null for a new one (POST). */
  id: number | null;
  name: string;
  goal: ProgramGoal;
  weeks: string;
  days: DraftDay[];
}

let counter = 0;
const key = () => `k${++counter}`;

const s = (v: number | string | null | undefined) => (v === null || v === undefined ? "" : String(v));

export function fromPreview(preview: ProgramPreview): DraftProgram {
  const program = preview.program;
  return {
    id: null,
    name: program.name,
    goal: program.goal,
    weeks: s(program.weeks),
    days: program.days.map((day, d) => ({
      key: key(),
      name: day.name,
      exercises: day.exercises.map((e, i) => {
        const shown = preview.days[d]?.exercises[i];
        return {
          key: key(),
          exerciseId: e.exercise_id,
          name: shown?.exercise_id === e.exercise_id ? shown.name : `#${e.exercise_id}`,
          equipment: "",
          sets: s(e.sets),
          repMin: s(e.rep_min),
          repMax: s(e.rep_max),
          restSeconds: s(e.rest_seconds),
          startWeightKg: s(e.start_weight_kg),
          progression: e.progression ?? "double",
        };
      }),
    })),
  };
}

export function fromProgram(program: ProgramOut): DraftProgram {
  return {
    id: program.id,
    name: program.name,
    goal: program.goal,
    weeks: s(program.weeks),
    days: program.days.map((day) => ({
      key: key(),
      name: day.name,
      exercises: day.exercises.map((e) => ({
        key: key(),
        exerciseId: e.exercise.id,
        name: e.exercise.name,
        equipment: e.exercise.equipment,
        sets: s(e.sets),
        repMin: s(e.rep_min),
        repMax: s(e.rep_max),
        restSeconds: s(e.rest_seconds),
        startWeightKg: s(e.start_weight_kg),
        progression: e.progression,
      })),
    })),
  };
}

export function newExercise(exercise: Exercise): DraftExercise {
  return {
    key: key(),
    exerciseId: exercise.id,
    name: exercise.name,
    equipment: exercise.equipment,
    sets: "3",
    repMin: "8",
    repMax: "12",
    restSeconds: "90",
    startWeightKg: "",
    progression: "double",
  };
}

/** Moves item `index` by `delta` (−1 up, +1 down); out of range is a no-op. */
export function move<T>(items: readonly T[], index: number, delta: number): T[] {
  const target = index + delta;
  if (index < 0 || index >= items.length || target < 0 || target >= items.length) return [...items];
  const copy = [...items];
  const [item] = copy.splice(index, 1);
  copy.splice(target, 0, item as T);
  return copy;
}

function int(value: string, min: number, max: number): number | null {
  const n = Number(value.trim());
  return value.trim() !== "" && Number.isInteger(n) && n >= min && n <= max ? n : null;
}

/** A field the API would refuse: a message key of `training.programs.errors`, with its place. */
export interface DraftError {
  key: "name" | "weeks" | "days" | "dayName" | "tooMany" | "sets" | "reps" | "repsOrder" | "rest" | "weight";
  day?: number;
  name?: string;
}

export type Checked = { ok: true; body: ProgramIn } | { ok: false; errors: DraftError[] };

/** The API's limits, checked before sending so the form can say which field is off. */
export function toProgramIn(draft: DraftProgram): Checked {
  const errors: DraftError[] = [];
  const weeks = int(draft.weeks, 1, 52);
  if (!draft.name.trim()) errors.push({ key: "name" });
  if (weeks === null) errors.push({ key: "weeks" });
  if (draft.days.length === 0 || draft.days.length > 7) errors.push({ key: "days" });
  const days = draft.days.map((day, d) => {
    const where = { day: d + 1 };
    if (!day.name.trim()) errors.push({ key: "dayName", ...where });
    if (day.exercises.length > 20) errors.push({ key: "tooMany", ...where });
    return {
      name: day.name.trim(),
      exercises: day.exercises.map((e) => {
        const at = { ...where, name: e.name };
        const sets = int(e.sets, 1, 10);
        const repMin = int(e.repMin, 1, 100);
        const repMax = int(e.repMax, 1, 100);
        const rest = int(e.restSeconds, 0, 900);
        const weightText = e.startWeightKg.trim().replace(",", ".");
        const weight = weightText === "" ? null : Number(weightText);
        if (sets === null) errors.push({ key: "sets", ...at });
        if (repMin === null || repMax === null) errors.push({ key: "reps", ...at });
        else if (repMin > repMax) errors.push({ key: "repsOrder", ...at });
        if (rest === null) errors.push({ key: "rest", ...at });
        if (weight !== null && (!Number.isFinite(weight) || weight < 0 || weight > 500 || Math.round(weight * 4) !== weight * 4)) {
          errors.push({ key: "weight", ...at });
        }
        return {
          exercise_id: e.exerciseId,
          sets: sets ?? 0,
          rep_min: repMin ?? 0,
          rep_max: repMax ?? 0,
          rest_seconds: rest ?? 0,
          start_weight_kg: weight,
          progression: e.progression,
        };
      }),
    };
  });
  if (errors.length > 0) return { ok: false, errors };
  return { ok: true, body: { name: draft.name.trim(), goal: draft.goal, weeks: weeks ?? 8, days } };
}
