import { render } from "@testing-library/react";
import axe from "axe-core";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { ActivityDetailCard } from "@/components/activities/activity-detail";
import { ActivityFiltersForm } from "@/components/activities/activity-filters";
import { ActivityList } from "@/components/activities/activity-list";
import { WeeklySkeleton } from "@/components/dashboard/blocks";
import { DashboardFilters } from "@/components/dashboard/filters";
import { KpiTiles } from "@/components/dashboard/kpi-tiles";
import { SportBreakdown } from "@/components/dashboard/sport-breakdown";
import { WeeklyChart } from "@/components/dashboard/weekly-chart";
import { LoginForm } from "@/components/login-form";
import { SyncStatusView } from "@/components/sync/sync-status-view";
import { AddFood } from "@/components/nutrition/add-food";
import { MealList } from "@/components/nutrition/meal-list";
import { ProfileForm } from "@/components/nutrition/profile-form";
import { DailyRings, EnergyBalanceCard, WeeklyAverages } from "@/components/nutrition/summary-cards";
import { HistoryList } from "@/components/training/history-list";
import { PlateBar } from "@/components/training/plate-bar";
import { PrBoard } from "@/components/training/pr-board";
import { ExerciseProgressChart, WeeklyMuscleChart } from "@/components/training/progress-charts";
import { ProgramBuilder } from "@/components/training/program-builder";
import { RestTimerPanel } from "@/components/training/rest-timer";
import { WorkoutScreen } from "@/components/training/workout-screen";
import { WorkoutSummaryCard } from "@/components/training/workout-summary";
import { ErrorState } from "@/components/ui";
import { activity, page, summary, syncStatus, week } from "./support/fixtures";
import { CHICKEN, OATS, UNKNOWN_EXERCISE, daySummary, entry, profile, weekly } from "./support/nutrition-fixtures";
import { BENCH, CURL, PLATES_MIXED, memoryStore, workout } from "./support/training-fixtures";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
}));

async function violations(ui: ReactElement): Promise<string[]> {
  const { container } = render(<main>{ui}</main>);
  const result = await axe.run(container, {
    // jsdom cannot compute colours; contrast is covered by the design tokens.
    rules: { "color-contrast": { enabled: false } },
  });
  return result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

const RANGE = { preset: "12w" as const, from: "2026-07-27", to: "2026-10-18" };

describe("accessibility (axe)", () => {
  it.each<[string, ReactElement]>([
    ["dashboard filters", <DashboardFilters key="f" range={RANGE} sports={["Ride", "Run"]} />],
    ["KPI tiles", <KpiTiles key="k" summary={summary()} />],
    ["weekly chart", <WeeklyChart key="w" weeks={[week("2026-09-07"), week("2026-09-14", 2, 21_000)]} />],
    ["weekly skeleton", <WeeklySkeleton key="s" />],
    ["sport breakdown", <SportBreakdown key="b" summary={summary()} />],
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
        initial={{ items: [{ id: 1, program_day_id: null, program_day_name: null, started_at: "2026-10-18T17:30:00Z", ended_at: null, notes: "", set_count: 3, exercise_count: 1, volume_kg: 1200 }], next_cursor: "c" }}
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
