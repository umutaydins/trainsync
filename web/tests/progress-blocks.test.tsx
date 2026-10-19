import { fireEvent, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BodyBlock, NutritionBlock } from "@/features/progress/components/habit-blocks";
import { EnduranceBlock } from "@/features/progress/components/endurance-block";
import { KcalChart } from "@/features/progress/components/kcal-chart";
import { LiftsBlock, PrList, liftsOf } from "@/features/progress/components/lifts-block";
import { ProgressView } from "@/features/progress/components/progress-view";
import { StrengthBlock } from "@/features/progress/components/strength-block";
import { VolumeChart } from "@/features/progress/components/volume-chart";
import { WeightChart } from "@/features/progress/components/weight-chart";
import { YearHeatmap } from "@/features/progress/components/year-heatmap";
import { paceChangePct } from "@/features/progress/format";
import { heatmapGrid, level, moveFocus } from "@/features/progress/heatmap";
import type { ProgressData } from "@/features/progress/load";
import { renderWithIntl } from "./support/intl";
import {
  ALL_RECORDS,
  allTimeSummary,
  change,
  emptySummary,
  heatmap,
  progressSummary,
  record,
  records,
  series,
  weightSeries,
} from "./support/progress-fixtures";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace, refresh: vi.fn() }), usePathname: () => "/progress" }));

beforeEach(() => {
  replace.mockClear();
  // Reduced motion: numbers render final, charts do not animate.
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("reduce"), addEventListener: () => undefined, removeEventListener: () => undefined }));
});

function progressData(overrides: Partial<ProgressData> = {}): ProgressData {
  return {
    query: { period: "month" },
    today: "2026-10-19",
    summary: { ok: true, data: progressSummary() },
    distance: { ok: true, data: series("distance_m", [5000, 0, 10_000]) },
    tonnage: { ok: true, data: series("tonnage_kg", [0, 4120, 0]) },
    weight: { ok: true, data: weightSeries() },
    kcal: { ok: true, data: series("kcal", [2300, 0, 2600], { target: 2500 }) },
    heatmap: { ok: true, data: heatmap() },
    prs: { ok: true, data: records([ALL_RECORDS[0]!], { period: "month" }) },
    allPrs: { ok: true, data: records(ALL_RECORDS) },
    ...overrides,
  };
}

const term = (name: string) => screen.getAllByText(name, { selector: "dt" })[0]!.parentElement!;

describe("stat cards", () => {
  it("show big numbers with the change against the previous period", () => {
    renderWithIntl(<EnduranceBlock endurance={progressSummary().endurance} period="month" />);
    const distance = screen.getByTestId("stat-distance");
    expect(distance).toHaveTextContent("98.4");
    expect(distance).toHaveTextContent("km");
    expect(within(distance).getByLabelText("up 18% vs previous period")).toHaveClass("text-ok");
    // Less elevation is shown as a drop.
    expect(within(term("Elevation")).getByLabelText("down 17% vs previous period")).toHaveClass("text-bad");
  });

  it("show a pace for runs (faster is a drop in min/km, and good news) and a speed for rides", () => {
    renderWithIntl(<EnduranceBlock endurance={progressSummary().endurance} period="month" />);
    const run = document.querySelector('[data-group="run"]') as HTMLElement;
    expect(run).toHaveTextContent("5:20");
    expect(run).toHaveTextContent("/km");
    expect(within(run).getByLabelText("down 6% vs previous period")).toHaveClass("text-ok");
    const ride = document.querySelector('[data-group="ride"]') as HTMLElement;
    expect(ride).toHaveTextContent("28.8");
    expect(ride).toHaveTextContent("km/h");
    expect(paceChangePct(change(null, 3))).toBeNull();
  });

  it("have no change badges for all time", () => {
    renderWithIntl(<EnduranceBlock endurance={allTimeSummary().endurance} period="all" />);
    expect(screen.getByTestId("stat-distance")).toHaveTextContent("98.4");
    expect(screen.queryByLabelText(/vs previous period/)).not.toBeInTheDocument();
  });

  it("strength: sessions, tonnage, PRs, the adherence ring and sets per muscle", () => {
    renderWithIntl(<StrengthBlock strength={progressSummary().strength} period="month" />);
    expect(screen.getByTestId("stat-sessions")).toHaveTextContent("6");
    expect(screen.getByRole("progressbar", { name: "Upper/Lower 4-day: 75% of the planned sessions done" })).toHaveAttribute("aria-valuenow", "75");
    expect(screen.getByText("6 of 8 sessions")).toBeInTheDocument();
    expect(screen.getByTestId("muscle-bars")).toHaveAttribute("aria-label", "Sets per muscle: Back 30, Chest 24.");
  });

  it("food and body stay neutral: no good/bad colours, body fat is coming soon", () => {
    const s = progressSummary();
    renderWithIntl(
      <>
        <NutritionBlock nutrition={s.nutrition} period="month" />
        <BodyBlock body={s.body} period="month" />
      </>,
    );
    expect(screen.getByTestId("stat-kcal")).toHaveTextContent("2,480");
    expect(screen.getByText("Target 2,500 kcal")).toBeInTheDocument();
    expect(screen.getByText("Days above 50 g sugar")).toBeInTheDocument();
    const weightChange = within(term("Change")).getByLabelText(/vs previous period/);
    expect(weightChange).toHaveClass("text-muted");
    expect(within(term("Avg energy")).getByLabelText("down 5% vs previous period")).toHaveClass("text-muted");
    expect(term("Body fat")).toHaveTextContent("Coming soon");
  });
});

describe("charts", () => {
  it("volume: bars per bucket with a summary, switchable to tonnage", () => {
    renderWithIntl(<VolumeChart distance={series("distance_m", [5000, 0, 10_000])} tonnage={series("tonnage_kg", [0, 4120, 0])} />);
    const figure = screen.getByTestId("volume-chart");
    expect(figure).toHaveAttribute("aria-label", "Distance: 15 km in total, 3 bars.");
    expect(within(figure).getAllByRole("row")).toHaveLength(4);
    fireEvent.click(screen.getByRole("radio", { name: "Tonnage" }));
    expect(screen.getByTestId("volume-chart")).toHaveAttribute("aria-label", "Tonnage: 4,120 kg in total, 3 bars.");
  });

  it("volume: an empty period draws nothing", () => {
    renderWithIntl(<VolumeChart distance={series("distance_m", [0, 0])} tonnage={null} />);
    expect(screen.getByText("No distance in this period.")).toBeInTheDocument();
    expect(screen.queryByTestId("volume-chart")).not.toBeInTheDocument();
  });

  it("weight: weigh-ins and the moving average, in the table too", () => {
    renderWithIntl(<WeightChart series={weightSeries()} />);
    const figure = screen.getByTestId("weight-chart");
    expect(figure).toHaveAttribute("aria-label", "Weight: 4 weigh-ins, from 81.4 kg to 80.6 kg.");
    expect(within(figure).getAllByRole("row")).toHaveLength(5);
    expect(screen.getByText("7-day average")).toBeInTheDocument();
  });

  it("kcal: logged days only, against the target", () => {
    renderWithIntl(<KcalChart series={series("kcal", [2300, 0, 2600], { target: 2500 })} />);
    expect(screen.getByTestId("kcal-chart")).toHaveAttribute(
      "aria-label",
      "Energy logged on 2 days, 2,450 kcal per logged day on average; the daily target is 2,500 kcal.",
    );
    renderWithIntl(<KcalChart series={series("kcal", [0, 0])} />);
    expect(screen.getByText("No food logged in this period.")).toBeInTheDocument();
  });

  it("sport groups as labelled bars", () => {
    renderWithIntl(<EnduranceBlock endurance={progressSummary().endurance} period="month" />);
    expect(screen.getByTestId("sport-bars")).toHaveAttribute("aria-label", "Distance per sport: Run 86.4 km, Ride 12 km.");
  });

  it("e1RM: the lift's records over time, and the picker moves the URL", () => {
    renderWithIntl(
      <LiftsBlock
        allRecords={{ ok: true, data: records(ALL_RECORDS) }}
        periodRecords={{ ok: true, data: records([ALL_RECORDS[0]!]) }}
        exercises={progressSummary().strength.by_exercise}
        query={{ period: "month" }}
      />,
    );
    expect(screen.getByTestId("e1rm-chart")).toHaveAttribute("aria-label", "Bench Press: 2 records, best estimated 1RM 101.7 kg on Oct 16, 2026.");
    fireEvent.change(screen.getByLabelText("Lift"), { target: { value: "2" } });
    expect(replace).toHaveBeenCalledWith("/progress?period=month&lift=2#lift-chart", { scroll: false });
    expect(liftsOf(ALL_RECORDS, []).map((l) => l.name)).toEqual(["Bench Press", "Squat"]);
  });
});

describe("heatmap", () => {
  it("lays out weeks as columns and scales intensity from the busiest day", () => {
    const grid = heatmapGrid(heatmap().days);
    expect(grid.weeks).toBe(53);
    expect(grid.rows[3]![0]?.day).toBe("2026-01-01"); // a Thursday
    expect(grid.months).toHaveLength(12);
    expect([level(0, 100), level(1, 100), level(60, 100), level(100, 100)]).toEqual([0, 1, 3, 4]);
    expect(moveFocus(10, "ArrowRight", 365)).toBe(17);
    expect(moveFocus(2, "ArrowLeft", 365)).toBe(0);
    expect(moveFocus(2, "Enter", 365)).toBeNull();
  });

  it("labels every day and moves with the arrow keys", () => {
    renderWithIntl(<YearHeatmap heatmap={heatmap()} today="2026-10-19" firstYear={2024} query={{ period: "month" }} />);
    const grid = screen.getByRole("grid", { name: "Training minutes per day in 2026" });
    const today = within(grid).getByRole("gridcell", { name: "Mon, Oct 19: 182 min, 1 session, check-in done" });
    expect(today).toHaveAttribute("tabindex", "0");
    expect(today).toHaveAttribute("data-level", "4");
    today.focus();
    fireEvent.keyDown(today, { key: "ArrowLeft" });
    const before = within(grid).getByRole("gridcell", { name: "Mon, Oct 12: 65 min, 1 session, check-in done" });
    expect(before).toHaveFocus();
    expect(before).toHaveAttribute("data-level", "2");
    expect(screen.getByTestId("heatmap-day")).toHaveTextContent("Mon, Oct 12");
    fireEvent.keyDown(before, { key: "ArrowUp" });
    expect(within(grid).getByRole("gridcell", { name: "Sun, Oct 11: no training" })).toHaveFocus();
    expect(screen.getByRole("link", { name: "Show 2025" })).toHaveAttribute("href", "/progress?period=month&year=2025");
    expect(screen.queryByRole("link", { name: "Show 2027" })).not.toBeInTheDocument();
  });
});

describe("PR list", () => {
  it("lists the newest first with the previous record, linking to the lift's chart", () => {
    renderWithIntl(<PrList records={[record(), record({ workout_id: 1, achieved_at: "2026-08-01T17:00:00Z", e1rm_kg: 100, previous_kg: null })]} query={{ period: "all" }} />);
    const items = within(screen.getByTestId("pr-list")).getAllByRole("link");
    expect(items[0]).toHaveTextContent("Bench Press");
    expect(items[0]).toHaveTextContent("101.7 kg");
    expect(items[0]).toHaveTextContent("was 100 kg");
    expect(items[1]).toHaveTextContent("first record");
    expect(items[0]).toHaveAttribute("href", "/progress?period=all&lift=1#lift-chart");
  });

  it("says so when the period has none", () => {
    renderWithIntl(<PrList records={[]} query={{ period: "week" }} />);
    expect(screen.getByText("No new records in this period.")).toBeInTheDocument();
  });
});

describe("progress page", () => {
  it("renders every block for the period", () => {
    renderWithIntl(<ProgressView data={progressData()} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Progress");
    expect(screen.getByText("Oct 1 – 19, 2026 · vs Sep 1 – 19, 2026")).toBeInTheDocument();
    const blocks = [...document.querySelectorAll("[data-block]")];
    expect(blocks.map((b) => b.getAttribute("data-block"))).toEqual(["volume", "endurance", "strength", "lift-chart", "consistency", "nutrition", "body"]);
    expect(blocks.every((b) => b.getAttribute("data-period") === "month")).toBe(true);
  });

  it("a failing call is one block's error, the rest stays", () => {
    renderWithIntl(
      <ProgressView
        data={progressData({ kcal: { ok: false, status: 502, error: "kcal down" }, heatmap: { ok: false, status: 502, error: "heatmap down" } })}
      />,
    );
    const alerts = screen.getAllByRole("alert");
    expect(alerts.map((a) => a.textContent)).toEqual(["Could not load this blockheatmap down", "Could not load this blockkcal down"]);
    expect(screen.getByTestId("weight-chart")).toBeInTheDocument();
  });

  it("a failing summary keeps every summary block with its error", () => {
    renderWithIntl(<ProgressView data={progressData({ summary: { ok: false, status: 502, error: "down" } })} />);
    expect(screen.getAllByRole("alert")).toHaveLength(5);
    expect(screen.getByTestId("volume-chart")).toBeInTheDocument();
  });

  it("a fresh account gets one friendly card with the ways to start", () => {
    renderWithIntl(
      <ProgressView
        data={progressData({
          summary: { ok: true, data: emptySummary() },
          heatmap: { ok: true, data: heatmap(2026, {}) },
          allPrs: { ok: true, data: records([]) },
        })}
      />,
    );
    expect(screen.getByText("Nothing here yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Connect Strava" })).toHaveAttribute("href", "/me/connections");
    expect(screen.getByRole("link", { name: "Start a workout" })).toHaveAttribute("href", "/training");
    expect(screen.getByRole("link", { name: "Log food" })).toHaveAttribute("href", "/nutrition");
    expect(document.querySelector("[data-block]")).toBeNull();
  });

  it("an empty period shows each block's own empty state", () => {
    renderWithIntl(<ProgressView data={progressData({ summary: { ok: true, data: emptySummary() } })} />);
    expect(screen.getByText("No activities in this period.")).toBeInTheDocument();
    expect(screen.getByText("No workouts in this period.")).toBeInTheDocument();
    expect(screen.getAllByText("No food logged in this period.").length).toBeGreaterThan(0);
  });

  it("speaks Turkish", () => {
    renderWithIntl(<ProgressView data={progressData()} />, "tr");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("İlerleme");
    expect(screen.getByRole("heading", { name: "Dayanıklılık" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Kuvvet" })).toBeInTheDocument();
    expect(screen.getByTestId("stat-distance")).toHaveTextContent("98,4");
  });

  it("an empty food or body block shows its empty message once, without the chart", () => {
    const s = progressSummary();
    const noFood = { ...s.nutrition, logged_days: { ...s.nutrition.logged_days, value: 0 } };
    renderWithIntl(
      <>
        <NutritionBlock nutrition={noFood} period="month">
          <p>food chart</p>
        </NutritionBlock>
        <BodyBlock body={{ ...s.body, last_kg: null }} period="month">
          <p>weight chart</p>
        </BodyBlock>
      </>,
    );
    expect(screen.queryByText("food chart")).not.toBeInTheDocument();
    expect(screen.queryByText("weight chart")).not.toBeInTheDocument();
  });
});
