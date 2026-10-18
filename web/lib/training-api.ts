import "server-only";

import { cache } from "react";

import { getJson } from "@/lib/api";
import type {
  BodyMetricList,
  ExerciseList,
  ExerciseProgress,
  ProgramList,
  ProgramOut,
  RecordList,
  WeeklyVolume,
  WorkoutDetail,
  WorkoutPage,
} from "@/lib/training-types";

/** Typed `/v1/training` reads for server components (same path as the BFF, ADR 0011). */
export const trainingApi = {
  exercises: cache(() => getJson<ExerciseList>("/v1/training/exercises")),
  programs: cache(() => getJson<ProgramList>("/v1/training/programs")),
  program: cache((id: number) => getJson<ProgramOut>(`/v1/training/programs/${id}`)),
  activeProgram: cache(() => getJson<ProgramOut>("/v1/training/programs/active")),
  workouts: cache((limit = 20, cursor?: string) => getJson<WorkoutPage>("/v1/training/workouts", { limit, cursor })),
  workout: cache((id: number) => getJson<WorkoutDetail>(`/v1/training/workouts/${id}`)),
  exerciseProgress: cache((id: number, from?: string, to?: string) =>
    getJson<ExerciseProgress>(`/v1/training/exercises/${id}/progress`, { from, to }),
  ),
  weeklyVolume: cache((from?: string, to?: string) => getJson<WeeklyVolume>("/v1/training/volume/weekly", { from, to })),
  records: cache(() => getJson<RecordList>("/v1/training/prs")),
  bodyMetrics: cache((from?: string, to?: string) => getJson<BodyMetricList>("/v1/training/body-metrics", { from, to })),
};
