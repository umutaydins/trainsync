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
import { ErrorState } from "@/components/ui";
import { activity, page, summary, syncStatus, week } from "./support/fixtures";

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
  ])("%s has no violations", async (_name, ui) => {
    expect(await violations(ui)).toEqual([]);
  });
});
