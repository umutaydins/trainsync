import "server-only";

import { nutritionApi } from "@/features/nutrition/api";
import type { DaySummary } from "@/features/nutrition/types";
import { progressApi } from "@/features/progress/api";
import { localDay, localHour } from "@/features/progress/format";
import type { ProgressSummary } from "@/features/progress/types";
import { settingsApi } from "@/features/settings/api";
import type { StravaConnection } from "@/features/settings/types";
import { trainingApi } from "@/features/training/api";
import type { ProgramOut, WorkoutPage } from "@/features/training/types";
import { type Loaded, api, load } from "@/lib/api";
import type { ActivityPage, Me } from "@/lib/types";

/** Open workouts are among the latest few. */
const RECENT_WORKOUTS = 5;

export interface TodayData {
  /** Today in the user's zone (`YYYY-MM-DD`) and the local hour, for the greeting. */
  today: string;
  hour: number;
  now: Date;
  me: Loaded<Me>;
  week: Loaded<ProgressSummary>;
  program: Loaded<ProgramOut>;
  workouts: Loaded<WorkoutPage>;
  food: Loaded<DaySummary>;
  latest: Loaded<ActivityPage>;
  strava: Loaded<StravaConnection>;
}

/** Every read of Today in parallel, each on its own (one failing block is one error state). */
export async function loadToday(now: Date, timeZone: string): Promise<TodayData> {
  const today = localDay(now, timeZone);
  const [me, week, program, workouts, food, latest, strava] = await Promise.all([
    load(() => api.me()),
    load(() => progressApi.summary("week")),
    load(() => trainingApi.activeProgram()),
    load(() => trainingApi.workouts(RECENT_WORKOUTS)),
    load(() => nutritionApi.summary(today)),
    load(() => api.activities({ limit: 1 })),
    load(() => settingsApi.strava()),
  ]);
  return { today, hour: localHour(now, timeZone), now, me, week, program, workouts, food, latest, strava };
}
