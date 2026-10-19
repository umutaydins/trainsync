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

/** Workouts per history page (server render and "Load more"). */
export const HISTORY_PAGE_SIZE = 20;

export const GOALS: readonly ProgramGoal[] = ["strength", "hypertrophy", "general"];
