import type { components } from "@/lib/api-types";

type Schemas = components["schemas"];

export type Exercise = Schemas["ExerciseOut"];
export type ExerciseList = Schemas["ExerciseList"];
export type Equipment = Schemas["Equipment"];
export type Muscle = Schemas["Muscle"];
export type ProgramGoal = Schemas["ProgramGoal"];
export type GenerateIn = Schemas["GenerateIn"];
export type ProgramPreview = Schemas["ProgramPreview"];
export type ProgramIn = Schemas["ProgramIn-Input"];
export type PlannedExerciseIn = Schemas["PlannedExerciseIn-Input"];
export type ProgramOut = Schemas["ProgramOut"];
export type ProgramSummary = Schemas["ProgramSummary"];
export type ProgramList = Schemas["ProgramList"];
export type WorkoutDetail = Schemas["WorkoutDetail"];
export type WorkoutSummary = Schemas["WorkoutSummary"];
export type WorkoutPage = Schemas["WorkoutPage"];
export type PlannedExercise = Schemas["PlannedExercise"];
export type SetIn = Schemas["SetIn"];
export type SetOut = Schemas["SetOut"];
export type WorkoutRecord = Schemas["RecordOut"];
export type PlatesOut = Schemas["PlatesOut"];
export type ExerciseProgress = Schemas["ExerciseProgress"];
export type WeeklyVolume = Schemas["WeeklyVolume"];
export type MuscleWeek = Schemas["MuscleWeek"];
export type RecordList = Schemas["RecordList"];
export type CurrentRecord = Schemas["CurrentRecord"];
export type BodyMetricList = Schemas["BodyMetricList"];
export type BodyMetric = Schemas["BodyMetricOut"];

export const EQUIPMENT: readonly Equipment[] = [
  "barbell",
  "dumbbell",
  "machine",
  "cable",
  "kettlebell",
  "band",
  "bodyweight",
];

export const GOALS: readonly ProgramGoal[] = ["strength", "hypertrophy", "general"];

/** `push_pull_legs` → `Push pull legs`. */
export function label(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** `12.5` → `12.5 kg`, `80` → `80 kg`. */
export function formatKg(kg: number, digits = 2): string {
  return `${kg.toLocaleString("en-GB", { maximumFractionDigits: digits })} kg`;
}

/** Whole kilograms with thousands separators, for volume totals: `8,240 kg`. */
export function formatVolume(kg: number): string {
  return `${Math.round(kg).toLocaleString("en-GB")} kg`;
}

export const PR_LABELS: Record<WorkoutRecord["kind"], string> = {
  weight_for_reps: "Weight for reps",
  e1rm: "Estimated 1RM",
  session_volume: "Session volume",
};

export function describeRecord(record: WorkoutRecord): string {
  if (record.kind === "weight_for_reps") return `${formatKg(record.value)} × ${record.reps ?? "?"}`;
  if (record.kind === "e1rm") return `${formatKg(record.value, 1)} e1RM`;
  return `${formatVolume(record.value)} volume`;
}
