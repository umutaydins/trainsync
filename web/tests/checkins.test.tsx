import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CheckinDayEditor } from "@/features/checkins/components/day-editor";
import { CheckinHeatmap } from "@/features/checkins/components/heatmap";
import { CheckinTiles } from "@/features/checkins/components/tiles";
import type { Checkin, CheckinStatus, CheckinSummary } from "@/features/checkins/checkins";
import { dayLabel, formatAdherence, heatmapWeeks, weekdayInitials } from "@/features/checkins/checkins";
import { violations } from "./support/axe";
import { renderWithIntl as render } from "./support/intl";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

/** The hand-computed fixture the API's tests use too (tests/fixtures/checkins.json). */
interface Case {
  from: string;
  to: string;
  planned: number;
  done: number;
  adherence: number;
  current_streak: number;
  longest_streak: number;
  counts: Record<CheckinStatus, number>;
  weeks: [string, number, number][];
}
const FIXTURE = JSON.parse(
  // vitest runs from web/; jsdom's import.meta.url is not a file URL.
  readFileSync(join(process.cwd(), "..", "tests", "fixtures", "checkins.json"), "utf8"),
) as { today: string; days_per_week: number; days: Record<string, CheckinStatus>; cases: [Case, Case] };
const [FULL_WEEKS, FROM_THURSDAY] = FIXTURE.cases;

function checkin(date: string, status: CheckinStatus, extra: Partial<Checkin> = {}): Checkin {
  return {
    date,
    status,
    workout_id: null,
    reason_note: null,
    sleep_hours: null,
    energy_1_5: null,
    body_weight_kg: null,
    created_at: `${date}T18:00:00Z`,
    updated_at: `${date}T18:00:00Z`,
    ...extra,
  };
}

function itemsIn(from: string, to: string): Checkin[] {
  return Object.entries(FIXTURE.days)
    .filter(([day]) => day >= from && day <= to)
    .map(([day, status]) => checkin(day, status));
}

function summaryOf(c: Case): CheckinSummary {
  return {
    from: c.from,
    to: c.to,
    today: FIXTURE.today,
    current_streak: c.current_streak,
    longest_streak: c.longest_streak,
    days_per_week: FIXTURE.days_per_week,
    planned_days: c.planned,
    planned_days_done: c.done,
    adherence: c.adherence,
    counts: c.counts,
    weeks: c.weeks.map(([week_start, planned, done]) => ({ week_start, planned, done })),
  };
}

describe("check-in heatmap", () => {
  it("renders the hand-computed fixture: one cell per day, status by colour, glyph and label", () => {
    const { from, to, counts } = FULL_WEEKS;
    render(<CheckinHeatmap from={from} to={to} items={itemsIn(from, to)} selected="2026-10-12" />);
    const table = screen.getByRole("table", { name: `Check-ins ${dayLabel("en", from)} to ${dayLabel("en", to)}` });
    const cells = within(table).getAllByRole("link");
    expect(cells).toHaveLength(21); // three full ISO weeks
    const byStatus: Record<string, number> = {};
    for (const cell of cells) {
      const status = cell.getAttribute("data-status") ?? "";
      byStatus[status] = (byStatus[status] ?? 0) + 1;
    }
    expect(byStatus).toEqual({ ...counts, none: 2 }); // 4 Oct and today (18 Oct) are empty
    expect(screen.getByRole("link", { name: "Mon, Oct 5: Sick or injured" })).toHaveAttribute(
      "href",
      "?day=2026-10-05",
    );
    expect(screen.getByRole("link", { name: "Sun, Oct 4: No check-in" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Fri, Oct 2: Partly" })).toHaveTextContent("½");
    expect(screen.getByRole("link", { name: "Mon, Oct 12: Done" })).toHaveAttribute("aria-current", "date");
    const legend = screen.getByRole("list", { name: "Legend" });
    expect(within(legend).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "✓Done",
      "½Partly",
      "✕Skipped",
      "zRest day",
      "+Sick or injured",
      "No check-in",
    ]);
  });

  it("pads a range that starts mid-week to whole weeks", () => {
    const weeks = heatmapWeeks(FROM_THURSDAY.from, FROM_THURSDAY.to, itemsIn(FROM_THURSDAY.from, FROM_THURSDAY.to));
    expect(weeks.map((w) => w[0]?.day)).toEqual(FROM_THURSDAY.weeks.map(([monday]) => monday));
    const first = weeks[0] ?? [];
    expect(first.filter((c) => !c.inRange).map((c) => c.day)).toEqual(["2026-09-28", "2026-09-29", "2026-09-30"]);
    expect(first[3]).toEqual({ day: "2026-10-01", inRange: true, status: "skipped" });
  });
});

describe("streak and adherence tiles", () => {
  it("show the fixture's numbers", () => {
    render(<CheckinTiles summary={summaryOf(FULL_WEEKS)} />);
    const tiles = screen.getByTestId("checkin-tiles");
    expect(tiles).toHaveTextContent(/Check-in streak\s*13\s*days\s*longest 16 days/);
    expect(tiles).toHaveTextContent(/Adherence\s*88%\s*7 of 8 planned days/);
  });

  it("say so when no program is active", () => {
    render(<CheckinTiles summary={{ ...summaryOf(FULL_WEEKS), adherence: null, planned_days: 0, current_streak: 1 }} />);
    expect(screen.getByTestId("checkin-tiles")).toHaveTextContent("Adherence—no active program");
    expect(screen.getByTestId("checkin-tiles")).toHaveTextContent(/streak\s*1\s*day(?!s)/);
  });

  it("format helpers follow the language", () => {
    expect(formatAdherence("en", { adherence: 0.625 })).toBe("63%");
    expect(formatAdherence("tr", { adherence: 0.625 })).toBe("%63");
    expect(dayLabel("en", "2026-10-18")).toBe("Sun, Oct 18");
    expect(weekdayInitials("en")).toEqual(["M", "T", "W", "T", "F", "S", "S"]);
  });

  it("speak Turkish", () => {
    render(<CheckinTiles summary={summaryOf(FULL_WEEKS)} />, "tr");
    expect(screen.getByTestId("checkin-tiles")).toHaveTextContent("Kayıt serisi");
    expect(screen.getByTestId("checkin-tiles")).toHaveTextContent("planlanan 8 günden 7");
  });
});

describe("day editor", () => {
  it("saves the day with an idempotent PUT through the BFF", async () => {
    const save = vi.fn().mockResolvedValue({ ok: true, status: 200, data: null });
    const existing = checkin("2026-10-14", "done", { workout_id: 42, energy_1_5: 4 });
    render(<CheckinDayEditor day="2026-10-14" checkin={existing} save={save} />);
    expect(screen.getByRole("heading", { name: "Wed, Oct 14" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Done" })).toBeChecked();
    await userEvent.click(screen.getByRole("radio", { name: "Partly" }));
    await userEvent.type(screen.getByLabelText("Sleep (h)"), "7,5");
    await userEvent.type(screen.getByLabelText("Reason or note"), "short on time");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(save).toHaveBeenCalledWith("/v1/checkins/2026-10-14", {
      status: "partial",
      workout_id: 42,
      reason_note: "short on time",
      sleep_hours: 7.5,
      energy_1_5: 4,
      body_weight_kg: null,
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Saved.");
    expect(refresh).toHaveBeenCalled();
  });

  it("asks for a status and shows API errors", async () => {
    const save = vi.fn().mockResolvedValue({ ok: false, status: 422, error: "invalid" });
    render(<CheckinDayEditor day="2026-10-18" checkin={null} save={save} />);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a status.");
    expect(save).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("radio", { name: "Rest day" }));
    await userEvent.type(screen.getByLabelText("Scale (kg)"), "abc");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Sleep and scale must be numbers.");
    await userEvent.clear(screen.getByLabelText("Scale (kg)"));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Check the values.");
  });
});

describe("check-ins accessibility", () => {
  it("heatmap, tiles and editor have no axe violations", async () => {
    const { from, to } = FULL_WEEKS;
    expect(await violations(<CheckinHeatmap from={from} to={to} items={itemsIn(from, to)} selected="2026-10-12" />)).toEqual([]);
    cleanup();
    expect(await violations(<CheckinTiles summary={summaryOf(FULL_WEEKS)} />, "tr")).toEqual([]);
    cleanup();
    expect(await violations(<CheckinDayEditor day="2026-10-14" checkin={null} save={vi.fn()} />)).toEqual([]);
  });
});
