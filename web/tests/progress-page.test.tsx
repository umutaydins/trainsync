import { cleanup, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProgressLoading from "@/app/(app)/progress/loading";
import ProgressPage from "@/app/(app)/progress/page";
import { progressApi } from "@/features/progress/api";
import { BodyBlock, ConsistencyBlock, NutritionBlock } from "@/features/progress/components/habit-blocks";
import { KcalChart } from "@/features/progress/components/kcal-chart";
import { LiftsBlock } from "@/features/progress/components/lifts-block";
import { PeriodSwitcher } from "@/features/progress/components/period-switcher";
import { ProgressSkeleton } from "@/features/progress/components/progress-skeleton";
import { StrengthBlock } from "@/features/progress/components/strength-block";
import { VolumeChart } from "@/features/progress/components/volume-chart";
import { WeightChart } from "@/features/progress/components/weight-chart";
import { YearHeatmap } from "@/features/progress/components/year-heatmap";
import { EnduranceBlock } from "@/features/progress/components/endurance-block";
import { ApiError } from "@/lib/api";
import { violations } from "./support/axe";
import { renderWithIntl } from "./support/intl";
import { ALL_RECORDS, heatmap, progressSummary, records, series, weightSeries } from "./support/progress-fixtures";

const locale = vi.hoisted(() => ({ current: "en" as "en" | "tr" }));
vi.mock("next-intl/server", async () => {
  const { translatorFor } = await import("./support/intl");
  return {
    getTranslations: (namespace?: string) => translatorFor(locale.current)(namespace),
    getTimeZone: async () => "Europe/Berlin",
  };
});
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }), usePathname: () => "/progress" }));

beforeEach(() => {
  locale.current = "en";
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("reduce"), addEventListener: () => undefined, removeEventListener: () => undefined }));
  vi.spyOn(progressApi, "summary").mockResolvedValue(progressSummary());
  vi.spyOn(progressApi, "series").mockImplementation(async (metric) => (metric === "weight_kg" ? weightSeries() : series(metric, [1000, 2000])));
  vi.spyOn(progressApi, "heatmap").mockResolvedValue(heatmap());
  vi.spyOn(progressApi, "prs").mockResolvedValue(records(ALL_RECORDS));
});

describe("progress route", () => {
  it("reads every block for the URL's period, weight and kcal by day", async () => {
    renderWithIntl(await ProgressPage({ searchParams: Promise.resolve({ period: "custom", from: "2026-09-01", to: "2026-09-30", year: "2025" }) }));
    expect(progressApi.summary).toHaveBeenCalledWith("custom", "2026-09-01", "2026-09-30");
    expect(progressApi.series).toHaveBeenCalledWith("distance_m", "custom", "2026-09-01", "2026-09-30");
    expect(progressApi.series).toHaveBeenCalledWith("weight_kg", "custom", "2026-09-01", "2026-09-30", "day");
    expect(progressApi.series).toHaveBeenCalledWith("kcal", "custom", "2026-09-01", "2026-09-30", "day");
    expect(progressApi.heatmap).toHaveBeenCalledWith(2025);
    expect(progressApi.prs).toHaveBeenCalledWith("all");
    expect(screen.getByTestId("progress")).toHaveAttribute("data-period", "custom");
  });

  it("one failing call does not break the page", async () => {
    vi.mocked(progressApi.heatmap).mockRejectedValue(new ApiError(502, "heatmap down"));
    renderWithIntl(await ProgressPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent("heatmap down");
    expect(screen.getByTestId("volume-chart")).toBeInTheDocument();
  });

  it("a year in the future asks for this year", async () => {
    await ProgressPage({ searchParams: Promise.resolve({ year: "2099" }) });
    expect(progressApi.heatmap).toHaveBeenCalledWith(2026);
  });

  it("loading has the page's shape", async () => {
    locale.current = "tr";
    renderWithIntl(await ProgressLoading(), "tr");
    expect(screen.getByRole("status", { name: "İlerlemen yükleniyor" })).toBeInTheDocument();
  });
});

describe("accessibility (axe)", () => {
  const s = progressSummary();
  it.each<[string, ReactElement]>([
    ["switcher", <PeriodSwitcher key="p" query={{ period: "month" }} today="2026-10-19" />],
    ["endurance", <EnduranceBlock key="e" endurance={s.endurance} period="month" />],
    ["strength", <StrengthBlock key="s" strength={s.strength} period="month" />],
    ["consistency", <ConsistencyBlock key="c" consistency={s.consistency} period="month" />],
    ["nutrition", <NutritionBlock key="n" nutrition={s.nutrition} period="month" />],
    ["body", <BodyBlock key="b" body={s.body} period="month" />],
    ["volume", <VolumeChart key="v" distance={series("distance_m", [1000, 0])} tonnage={series("tonnage_kg", [0, 500])} />],
    ["weight", <WeightChart key="w" series={weightSeries()} />],
    ["kcal", <KcalChart key="k" series={series("kcal", [2000, 2500], { target: 2400 })} />],
    ["heatmap", <YearHeatmap key="h" heatmap={heatmap()} today="2026-10-19" firstYear={2025} query={{ period: "month" }} />],
    [
      "lifts",
      <LiftsBlock key="l" allRecords={{ ok: true, data: records(ALL_RECORDS) }} periodRecords={{ ok: true, data: records(ALL_RECORDS) }} exercises={s.strength.by_exercise} query={{ period: "month" }} />,
    ],
    ["skeleton", <ProgressSkeleton key="sk" label="Loading" />],
  ])("%s", async (_name, ui) => {
    expect(await violations(ui)).toEqual([]);
    cleanup();
    expect(await violations(ui, "tr")).toEqual([]);
  });
});
