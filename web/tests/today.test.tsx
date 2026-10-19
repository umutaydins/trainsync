import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TodayPage from "@/app/(app)/(today)/page";
import TodayLoading from "@/app/(app)/(today)/loading";
import { nutritionApi } from "@/features/nutrition/api";
import { progressApi } from "@/features/progress/api";
import { settingsApi } from "@/features/settings/api";
import { TodayView, dayPart } from "@/features/today/components/today-view";
import type { TodayData } from "@/features/today/load";
import { nextPlanned, plannedOn, weekdayOf, weekdayOfDate } from "@/features/today/schedule";
import { trainingApi } from "@/features/training/api";
import { ApiError, api } from "@/lib/api";
import { violations } from "./support/axe";
import { renderWithIntl } from "./support/intl";
import { daySummary } from "./support/nutrition-fixtures";
import { activities, emptySummary, program, progressSummary } from "./support/progress-fixtures";
import { me } from "./support/settings-fixtures";

const locale = vi.hoisted(() => ({ current: "en" as "en" | "tr" }));
vi.mock("next-intl/server", async () => {
  const { translatorFor } = await import("./support/intl");
  return {
    getTranslations: (namespace?: string) => translatorFor(locale.current)(namespace),
    getTimeZone: async () => "Europe/Berlin",
  };
});
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/" }));

const NOW = new Date("2026-10-19T07:30:00Z"); // Monday, 09:30 in Berlin
const NOT_FOUND = { ok: false as const, status: 404, error: "no active program" };

function todayData(overrides: Partial<TodayData> = {}): TodayData {
  return {
    today: "2026-10-19",
    hour: 9,
    now: NOW,
    me: { ok: true, data: me({ display_name: "Ayşe Yılmaz" }) },
    week: { ok: true, data: progressSummary({ period: "week" }) },
    program: { ok: true, data: program() },
    workouts: { ok: true, data: { items: [], next_cursor: null } },
    food: { ok: true, data: daySummary() },
    latest: { ok: true, data: activities(1) },
    strava: { ok: true, data: { connected: true } },
    ...overrides,
  };
}

function freshUser(): Partial<TodayData> {
  return {
    week: { ok: true, data: emptySummary() },
    program: NOT_FOUND,
    food: { ok: true, data: daySummary({ entry_count: 0, intake_kcal: 0, kcal_target: null, kcal_remaining: null }) },
    latest: { ok: true, data: activities(0) },
    strava: { ok: true, data: { connected: false } },
  };
}

beforeEach(() => {
  locale.current = "en";
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("reduce"), addEventListener: () => undefined, removeEventListener: () => undefined }));
});

describe("program schedule (the coach's weekday rule)", () => {
  it("uses a day's own weekday, else the default spread", () => {
    const p = program();
    expect(plannedOn(p, 0)?.name).toBe("Upper A");
    expect(plannedOn(p, 1)).toBeNull();
    expect(nextPlanned(p, 0)).toMatchObject({ weekday: 2, day: { name: "Lower A" } });
    expect(nextPlanned(p, 3)).toMatchObject({ weekday: 0, day: { name: "Upper A" } });
    const spread = program({ days_per_week: 3, days: program().days.map((d) => ({ ...d, weekday: null })) });
    expect(spread.days.map((d) => weekdayOf(d, 3))).toEqual([0, 2]);
    expect(weekdayOfDate("2026-10-19")).toBe(0);
    expect([dayPart(6), dayPart(13), dayPart(22), dayPart(2)]).toEqual(["morning", "afternoon", "evening", "evening"]);
  });
});

describe("Today", () => {
  it("full: greeting, today's workout, this week, food and the latest activity", () => {
    renderWithIntl(<TodayView data={todayData()} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Good morning, Ayşe");
    expect(screen.getByText("Monday, October 19")).toBeInTheDocument();
    expect(screen.getByTestId("sync-freshness")).toHaveTextContent("Synced");
    const workout = screen.getByTestId("today-workout");
    expect(workout).toHaveTextContent("Upper A");
    expect(workout).toHaveTextContent("Bench Press");
    expect(within(workout).getByRole("button", { name: "Start workout" })).toBeInTheDocument();
    const week = screen.getByTestId("today-week");
    expect(week).toHaveTextContent("98.4");
    expect(within(week).getAllByLabelText(/vs previous period/).length).toBeGreaterThan(0);
    expect(within(week).getByRole("link", { name: "Progress" })).toHaveAttribute("href", "/progress?period=week");
    expect(screen.getByRole("progressbar", { name: "1,890 of 2,400 kcal" })).toBeInTheDocument();
    expect(screen.getByText("510 kcal to the target")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Long run/ })).toHaveAttribute("href", "/activities/812");
  });

  it("continues an open workout instead of starting one", () => {
    const open = { id: 77, client_id: "c", program_day_id: 11, program_day_name: "Upper A", started_at: "2026-10-19T06:00:00Z", ended_at: null, notes: "", set_count: 4, exercise_count: 2, volume_kg: 1200 };
    renderWithIntl(<TodayView data={todayData({ workouts: { ok: true, data: { items: [open], next_cursor: null } } })} />);
    expect(screen.getByRole("link", { name: "Continue workout" })).toHaveAttribute("href", "/training/workout/77");
  });

  it("a rest day says what is next", () => {
    renderWithIntl(<TodayView data={todayData({ today: "2026-10-20" })} />);
    expect(screen.getByTestId("today-workout")).toHaveTextContent("Rest day");
    expect(screen.getByText("Next: Lower A on Wednesday")).toBeInTheDocument();
  });

  it("no program: a call to pick one", () => {
    renderWithIntl(<TodayView data={todayData({ program: NOT_FOUND })} />);
    expect(screen.getByText("No program yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose a program" })).toHaveAttribute("href", "/training");
  });

  it("fresh user without Strava: connect, log food, pick a program", () => {
    renderWithIntl(<TodayView data={todayData(freshUser())} />);
    expect(screen.getByRole("link", { name: "Connect Strava" })).toHaveAttribute("href", "/me/connections");
    expect(screen.getByText("Nothing logged today")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log food" })).toHaveAttribute("href", "/nutrition");
    expect(screen.getByTestId("sync-freshness")).toHaveTextContent("Not synced yet");
    expect(screen.queryByLabelText(/vs previous period/)).not.toBeInTheDocument();
  });

  it("connected to Strava but nothing synced yet", () => {
    renderWithIntl(<TodayView data={todayData({ latest: { ok: true, data: activities(0) } })} />);
    expect(screen.getByText("No activities yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open sync" })).toHaveAttribute("href", "/sync");
  });

  it("each block fails on its own", () => {
    const down = { ok: false as const, status: 502, error: "down" };
    renderWithIntl(<TodayView data={todayData({ week: down, food: down, latest: down, program: down })} />);
    expect(screen.getAllByRole("alert").map((a) => a.textContent)).toEqual([
      "Could not load your programdown",
      "Could not load this weekdown",
      "Could not load today’s fooddown",
      "Could not load your activitiesdown",
    ]);
  });

  it("speaks Turkish", () => {
    renderWithIntl(<TodayView data={todayData({ hour: 20 })} />, "tr");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("İyi akşamlar, Ayşe");
    expect(screen.getByText("19 Ekim Pazartesi")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Antrenmana başla" })).toBeInTheDocument();
    expect(screen.getByText("Bu hafta")).toBeInTheDocument();
  });

  it("the page reads every block for today in the user's zone", async () => {
    vi.spyOn(api, "me").mockResolvedValue(me());
    vi.spyOn(api, "activities").mockResolvedValue(activities(1));
    vi.spyOn(progressApi, "summary").mockResolvedValue(progressSummary({ period: "week" }));
    vi.spyOn(trainingApi, "activeProgram").mockRejectedValue(new ApiError(404, "no active program"));
    vi.spyOn(trainingApi, "workouts").mockResolvedValue({ items: [], next_cursor: null });
    vi.spyOn(nutritionApi, "summary").mockResolvedValue(daySummary());
    vi.spyOn(settingsApi, "strava").mockResolvedValue({ connected: true });
    vi.useFakeTimers({ now: new Date("2026-10-19T22:30:00Z"), toFake: ["Date"] });
    renderWithIntl(await TodayPage());
    vi.useRealTimers();
    expect(nutritionApi.summary).toHaveBeenCalledWith("2026-10-20"); // already Tuesday in Berlin
    expect(progressApi.summary).toHaveBeenCalledWith("week");
    expect(api.activities).toHaveBeenCalledWith({ limit: 1 });
    expect(screen.getByText("No program yet")).toBeInTheDocument();
  });

  it("loading has the page's shape", async () => {
    renderWithIntl(await TodayLoading());
    expect(screen.getByRole("status", { name: "Loading today" })).toBeInTheDocument();
  });

  it.each([
    ["full", "en", todayData()],
    ["full", "tr", todayData()],
    ["fresh", "en", todayData(freshUser())],
    ["no program", "tr", todayData({ program: NOT_FOUND })],
  ] as const)("is axe-clean (%s, %s)", async (_name, lang, data) => {
    expect(await violations(<TodayView data={data} />, lang)).toEqual([]);
  });
});
