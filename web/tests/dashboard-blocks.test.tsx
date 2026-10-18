import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { KpiBlock, LongestBlock, SportBlock, WeeklyBlock, WeeklySkeleton } from "@/components/dashboard/blocks";
import { CHART_HEIGHT, WeeklyChart } from "@/components/dashboard/weekly-chart";
import { ApiError, api } from "@/lib/api";
import type { DashboardRange } from "@/lib/range";
import { summary, week } from "./support/fixtures";

const RANGE: DashboardRange = { preset: "custom", from: "2026-09-07", to: "2026-10-04" };

beforeEach(() => {
  vi.spyOn(api, "summary");
  vi.spyOn(api, "weekly");
});

describe("KPI tiles", () => {
  it("shows totals from /v1/stats/summary for the range", async () => {
    vi.mocked(api.summary).mockResolvedValue(summary());
    render(await KpiBlock({ range: RANGE }));
    expect(api.summary).toHaveBeenCalledWith("2026-09-07", "2026-10-04", undefined);
    expect(screen.getByText("352.3 km")).toBeInTheDocument();
    expect(screen.getByText("20:43")).toBeInTheDocument();
    expect(screen.getByText("2,493 m")).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
  });

  it("shows an error state", async () => {
    vi.mocked(api.summary).mockRejectedValue(new ApiError(502, "trainsync API unavailable"));
    render(await KpiBlock({ range: RANGE }));
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load totals");
    expect(screen.getByRole("alert")).toHaveTextContent("trainsync API unavailable");
  });

  it("rethrows unexpected errors to the error boundary", async () => {
    vi.mocked(api.summary).mockRejectedValue(new TypeError("bug"));
    await expect(KpiBlock({ range: RANGE })).rejects.toThrow("bug");
  });
});

describe("weekly volume", () => {
  it("renders the chart in a fixed-height box", async () => {
    vi.mocked(api.weekly).mockResolvedValue({
      from: RANGE.from,
      to: RANGE.to,
      sport_type: null,
      weeks: [week("2026-09-07"), week("2026-09-14", 0, 0)],
      last_synced_at: null,
    });
    render(await WeeklyBlock({ range: RANGE }));
    expect(screen.getByTestId("weekly-chart")).toHaveStyle({ height: `${CHART_HEIGHT}px` });
    expect(screen.getByTestId("weekly-table").querySelectorAll("tbody tr")).toHaveLength(2);
  });

  it("shows an empty state when every week is zero", async () => {
    vi.mocked(api.weekly).mockResolvedValue({
      from: RANGE.from,
      to: RANGE.to,
      sport_type: null,
      weeks: [week("2026-09-07", 0, 0)],
      last_synced_at: null,
    });
    render(await WeeklyBlock({ range: RANGE }));
    expect(screen.getByText("No activities in this range")).toBeInTheDocument();
    expect(screen.queryByTestId("weekly-chart")).not.toBeInTheDocument();
  });

  it("shows an error state", async () => {
    vi.mocked(api.weekly).mockRejectedValue(new ApiError(400, "`to` is before `from`"));
    render(await WeeklyBlock({ range: RANGE }));
    expect(screen.getByRole("alert")).toHaveTextContent("`to` is before `from`");
  });

  it("does not shift layout: skeleton reserves the chart's height", () => {
    const { container } = render(<WeeklySkeleton />);
    const placeholder = screen.getByRole("status", { name: "Loading weekly volume" });
    expect(placeholder).toHaveStyle({ height: `${CHART_HEIGHT}px` });
    expect(container.querySelector('[style*="height"]')).toBe(placeholder);
  });

  it("switches metric without changing the box", async () => {
    const { rerender } = render(<WeeklyChart weeks={[week("2026-09-07")]} />);
    screen.getByRole("button", { name: "Time (h)" }).click();
    rerender(<WeeklyChart weeks={[week("2026-09-07")]} />);
    expect(screen.getByTestId("weekly-chart")).toHaveStyle({ height: `${CHART_HEIGHT}px` });
  });
});

describe("by sport and longest", () => {
  it("lists sports by moving time", async () => {
    vi.mocked(api.summary).mockResolvedValue(summary());
    render(await SportBlock({ range: RANGE }));
    const links = screen.getAllByRole("link").map((a) => a.textContent);
    expect(links).toEqual(["Run", "Ride", "Swim"]);
    expect(screen.getByRole("link", { name: "Run" })).toHaveAttribute(
      "href",
      "/activities?sport_type=Run&from=2026-09-07&to=2026-10-04",
    );
  });

  it("shows empty and error states", async () => {
    vi.mocked(api.summary).mockResolvedValueOnce(summary({ by_sport: [], longest: null }));
    const { unmount } = render(await SportBlock({ range: RANGE }));
    expect(screen.getByText("No activities in this range")).toBeInTheDocument();
    unmount();
    vi.mocked(api.summary).mockRejectedValueOnce(new ApiError(500, "boom"));
    render(await SportBlock({ range: RANGE }));
    expect(screen.getByRole("alert")).toHaveTextContent("boom");
  });

  it("links the longest activity", async () => {
    vi.mocked(api.summary).mockResolvedValue(summary());
    render(await LongestBlock({ range: RANGE }));
    expect(screen.getByRole("link")).toHaveAttribute("href", "/activities/7");
    expect(screen.getByText("100.0 km")).toBeInTheDocument();
  });
});
