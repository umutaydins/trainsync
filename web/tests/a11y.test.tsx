import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActivityDetailCard } from "@/features/activities/components/activity-detail";
import { ActivityFiltersForm } from "@/features/activities/components/activity-filters";
import { ActivityList } from "@/features/activities/components/activity-list";
import { LoginForm } from "@/features/auth/components/login-form";
import { SyncStatusView } from "@/features/sync/components/sync-status-view";
import { AddFood } from "@/features/nutrition/components/add-food";
import { MealList } from "@/features/nutrition/components/meal-list";
import { ProfileForm } from "@/features/nutrition/components/profile-form";
import { EnergyBalanceCard } from "@/features/nutrition/components/balance-card";
import { DailyRings } from "@/features/nutrition/components/totals-card";
import { WeeklyAverages } from "@/features/nutrition/components/week-card";
import { HistoryList } from "@/features/training/components/history-list";
import { PlateBar } from "@/features/training/components/plate-bar";
import { PrBoard } from "@/features/training/components/pr-board";
import { ExerciseProgressChart, WeeklyMuscleChart } from "@/features/training/components/progress-charts";
import { ProgramBuilder } from "@/features/training/components/program-builder";
import { RestTimerPanel } from "@/features/training/components/rest-timer";
import { WorkoutScreen } from "@/features/training/components/workout-screen";
import { WorkoutSummaryCard } from "@/features/training/components/workout-summary";
import { ErrorState } from "@/components/ui";
import { activity, page, syncStatus } from "./support/fixtures";
import { violations } from "./support/axe";
import { CHICKEN, OATS, UNKNOWN_EXERCISE, daySummary, entry, profile, weekly } from "./support/nutrition-fixtures";
import { BENCH, CURL, PLATES_MIXED, memoryStore, workout } from "./support/training-fixtures";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
}));

beforeEach(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("min-width"), addEventListener: () => undefined, removeEventListener: () => undefined }));
});

describe("accessibility (axe)", () => {
  it.each<[string, ReactElement]>([
    ["activity filters", <ActivityFiltersForm key="a" filters={{ sport_type: "Run" }} sports={["Ride", "Run"]} />],
    ["activity list", <ActivityList key="l" initial={page([1, 2], "c")} query={{}} />],
    ["activity detail", <ActivityDetailCard key="d" activity={activity(1)} />],
    ["login form", <LoginForm key="lf" next="/" />],
    ["error state", <ErrorState key="e" message="boom" />],
    ["sync status", <SyncStatusView key="ss" initial={syncStatus()} />],
    ["sync status (empty)", <SyncStatusView key="se" initial={syncStatus({ athletes: [], rate_limit: null })} />],
    ["workout screen", <WorkoutScreen key="ws" initial={workout()} exercises={[BENCH, CURL]} store={memoryStore()} />],
    [
      "rest timer",
      <RestTimerPanel key="rt" rest={{ endsAt: 90_000, durationS: 90, label: "Bench Press · set 1", alerted: false }} now={30_000} onAdjust={() => undefined} onSkip={() => undefined} />,
    ],
    ["plate drawing", <PlateBar key="pb" answer={PLATES_MIXED} />],
    ["workout summary", <WorkoutSummaryCard key="sum" workout={workout({ ended_at: "2026-10-18T18:35:00Z" })} />],
    ["program builder", <ProgramBuilder key="pbld" initial={[]} exercises={[BENCH, CURL]} />],
    [
      "workout history",
      <HistoryList
        key="hl"
        initial={{ items: [{ id: 1, client_id: "00000000-0000-4000-8000-000000000001", program_day_id: null, program_day_name: null, started_at: "2026-10-18T17:30:00Z", ended_at: null, notes: "", set_count: 3, exercise_count: 1, volume_kg: 1200 }], next_cursor: "c" }}
      />,
    ],
    [
      "exercise progress",
      <ExerciseProgressChart
        key="ep"
        progress={{ exercise: BENCH, sessions: [{ workout_id: 1, started_at: "2026-10-18T17:30:00Z", best_set: { reps: 8, weight_kg: 80, e1rm_kg: 101.3 }, e1rm_kg: 101.3, volume_kg: 1920, working_sets: 3 }] }}
      />,
    ],
    ["muscle volume", <WeeklyMuscleChart key="mv" items={[{ week_start: "2026-10-12", muscle: "chest", sets: 9, volume_kg: 7740 }]} />],
    [
      "records",
      <PrBoard key="pr" records={[{ exercise_id: 20, exercise_name: "Bench Press", kind: "e1rm", value: 101.3, previous: null, reps: null, workout_id: 1, achieved_at: "2026-10-18T17:30:00Z" }]} />,
    ],
    ["daily totals", <DailyRings key="dr" summary={daySummary()} />],
    ["energy balance", <EnergyBalanceCard key="eb" summary={daySummary(UNKNOWN_EXERCISE)} />],
    ["nutrition week", <WeeklyAverages key="nw" weekly={weekly()} />],
    ["meals", <MealList key="ml" entries={[entry()]} />],
    ["add food", <AddFood key="af" date="2026-10-18" favorites={[OATS]} recent={[CHICKEN]} />],
    ["profile form", <ProfileForm key="pf" profile={profile({ warning: "kcal_target is below the estimated basal metabolic rate." })} date="2026-10-18" />],
  ])("%s has no violations", async (_name, ui) => {
    expect(await violations(ui)).toEqual([]);
  });
});
