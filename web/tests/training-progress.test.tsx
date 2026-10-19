import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TrainingTilesBlock, gymWeek } from "@/features/dashboard/components/training-tiles";
import { HistoryList } from "@/features/training/components/history-list";
import { PrBoard } from "@/features/training/components/pr-board";
import { BodyWeightChart, ExerciseProgressChart, WeeklyMuscleChart, pivotWeeks } from "@/features/training/components/progress-charts";
import { WorkoutSets } from "@/features/training/components/workout-sets";
import { ApiError } from "@/lib/api";
import { nutritionApi } from "@/features/nutrition/api";
import { trainingApi } from "@/features/training/api";
import type { CurrentRecord, ExerciseProgress, MuscleWeek, WorkoutSummary } from "@/features/training/types";
import { jsonResponse } from "./support/env";
import { daySummary } from "./support/nutrition-fixtures";
import { BENCH, CURL, workout } from "./support/training-fixtures";

const PROGRESS: ExerciseProgress = {
  exercise: BENCH,
  sessions: [
    { workout_id: 40, started_at: "2026-10-08T17:30:00Z", best_set: { reps: 10, weight_kg: 75, e1rm_kg: 100 }, e1rm_kg: 100, volume_kg: 2250, working_sets: 3 },
    { workout_id: 41, started_at: "2026-10-15T17:30:00Z", best_set: { reps: 12, weight_kg: 77.5, e1rm_kg: 108.5 }, e1rm_kg: 108.5, volume_kg: 2790, working_sets: 3 },
    { workout_id: 42, started_at: "2026-10-18T17:30:00Z", best_set: { reps: 15, weight_kg: 60, e1rm_kg: null }, e1rm_kg: null, volume_kg: 2700, working_sets: 3 },
  ],
};

const WEEKS: MuscleWeek[] = [
  { week_start: "2026-10-05", muscle: "chest", sets: 6, volume_kg: 4500 },
  { week_start: "2026-10-05", muscle: "quads", sets: 8, volume_kg: 9600.5 },
  { week_start: "2026-10-12", muscle: "chest", sets: 9, volume_kg: 7740 },
  { week_start: "2026-10-12", muscle: "biceps", sets: 4, volume_kg: 520 },
];

const RECORDS: CurrentRecord[] = [
  { exercise_id: 20, exercise_name: "Bench Press", kind: "weight_for_reps", value: 77.5, previous: 75, reps: 12, workout_id: 41, achieved_at: "2026-10-15T17:30:00Z" },
  { exercise_id: 20, exercise_name: "Bench Press", kind: "e1rm", value: 108.5, previous: 100, reps: null, workout_id: 41, achieved_at: "2026-10-15T17:30:00Z" },
  { exercise_id: 1, exercise_name: "Back Squat", kind: "session_volume", value: 9600.5, previous: null, reps: null, workout_id: 39, achieved_at: "2026-10-06T17:30:00Z" },
];

function rowsData(testId: string, attrs: string[]) {
  return [...screen.getByTestId(testId).querySelectorAll("tbody tr")].map((tr) =>
    Object.fromEntries(attrs.map((a) => [a, tr.getAttribute(`data-${a}`)])),
  );
}

describe("progress charts render the API's numbers exactly", () => {
  it("exercise progress", () => {
    render(<ExerciseProgressChart progress={PROGRESS} />);
    expect(screen.getByTestId("exercise-chart")).toHaveAccessibleName("Bench Press: e1RM and best set per workout");
    expect(rowsData("exercise-table", ["workout", "best-weight", "best-reps", "e1rm", "volume"])).toEqual(
      PROGRESS.sessions.map((s) => ({
        workout: String(s.workout_id),
        "best-weight": String(s.best_set?.weight_kg),
        "best-reps": String(s.best_set?.reps),
        e1rm: s.e1rm_kg === null ? "" : String(s.e1rm_kg),
        volume: String(s.volume_kg),
      })),
    );
    const cells = [...screen.getByTestId("exercise-table").querySelectorAll("tbody tr")].map((tr) => tr.textContent);
    expect(cells[1]).toContain("12 × 77.5 kg");
    expect(cells[1]).toContain("108.5 kg");
    expect(cells[2]).toContain("—"); // no e1RM above 12 reps
  });

  it("weekly volume per muscle (stacked)", () => {
    render(<WeeklyMuscleChart items={WEEKS} />);
    expect(rowsData("muscle-table", ["week", "muscle", "sets", "volume"])).toEqual(
      WEEKS.map((w) => ({ week: w.week_start, muscle: w.muscle, sets: String(w.sets), volume: String(w.volume_kg) })),
    );
    const { rows, muscles } = pivotWeeks(WEEKS);
    expect(muscles).toEqual(["biceps", "chest", "quads"]);
    expect(rows).toEqual([
      { week: "2026-10-05", total: 14100.5, chest: 4500, quads: 9600.5 },
      { week: "2026-10-12", total: 8260, chest: 7740, biceps: 520 },
    ]);
  });

  it("records board", () => {
    render(<PrBoard records={RECORDS} />);
    expect(rowsData("pr-board", ["exercise", "kind", "value", "reps"])).toEqual(
      RECORDS.map((r) => ({ exercise: String(r.exercise_id), kind: r.kind, value: String(r.value), reps: r.reps === null ? "" : String(r.reps) })),
    );
    const text = screen.getByTestId("pr-board").textContent;
    expect(text).toContain("77.5 kg × 12");
    expect(text).toContain("108.5 kg e1RM");
    expect(text).toContain("9,601 kg volume");
  });

  it("body weight", () => {
    render(<BodyWeightChart items={[{ date: "2026-10-10", weight_kg: 78.9 }, { date: "2026-10-17", weight_kg: 78.45 }]} />);
    expect(rowsData("weight-table", ["date", "weight"])).toEqual([
      { date: "2026-10-10", weight: "78.9" },
      { date: "2026-10-17", weight: "78.45" },
    ]);
  });
});

describe("workout history", () => {
  const summary = (id: number, overrides: Partial<WorkoutSummary> = {}): WorkoutSummary => ({
    id,
    client_id: `00000000-0000-4000-8000-${String(id).padStart(12, "0")}`,
    program_day_id: 11,
    program_day_name: "Upper A",
    started_at: "2026-10-18T17:30:00Z",
    ended_at: "2026-10-18T18:35:00Z",
    notes: "",
    set_count: 14,
    exercise_count: 5,
    volume_kg: 8240,
    ...overrides,
  });

  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ items: [summary(40), summary(39, { ended_at: null })], next_cursor: null })));
  });

  it("lists workouts with volume and duration, and loads more by cursor", async () => {
    render(<HistoryList initial={{ items: [summary(42)], next_cursor: "abc" }} />);
    const list = screen.getByTestId("workout-history");
    expect(list).toHaveTextContent("8,240 kg");
    expect(list).toHaveTextContent("14 sets · 1:05:00");
    expect(screen.getByRole("link", { name: /Upper A/ })).toHaveAttribute("href", "/training/history/42");
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("End of list")).toBeInTheDocument();
    expect(String(vi.mocked(fetch).mock.calls[0]![0])).toBe("/api/ts/v1/training/workouts?limit=20&cursor=abc");
    expect(screen.getAllByRole("link")).toHaveLength(3);
    expect(screen.getAllByRole("link")[2]).toHaveAttribute("href", "/training/workout/39"); // still open
    expect(screen.getByTestId("workout-history")).toHaveTextContent("in progress");
  });

  it("detail lists the sets by exercise", () => {
    const detail = workout({
      sets: [
        { client_id: "a", workout_id: 42, exercise_id: 20, set_index: 1, reps: 8, weight_kg: 80, rpe: null, is_warmup: false, completed_at: "2026-10-18T17:40:00Z", rest_seconds: 90 },
        { client_id: "b", workout_id: 42, exercise_id: 20, set_index: 2, reps: 8, weight_kg: 80, rpe: null, is_warmup: false, completed_at: "2026-10-18T17:43:00Z", rest_seconds: 90 },
        { client_id: "c", workout_id: 42, exercise_id: 31, set_index: 1, reps: 12, weight_kg: 12.5, rpe: null, is_warmup: false, completed_at: "2026-10-18T17:50:00Z", rest_seconds: 60 },
      ],
    });
    render(<WorkoutSets workout={detail} exercises={new Map([[BENCH.id, BENCH], [CURL.id, CURL]])} />);
    expect(screen.getByRole("region", { name: "Bench Press" })).toHaveTextContent("1,280 kg");
    expect(screen.getByRole("region", { name: "Dumbbell Curl" })).toHaveTextContent("12 × 12.5 kg");
  });
});

describe("dashboard tiles", () => {
  const w = (id: number, started: string, volume: number): WorkoutSummary => ({
    id,
    client_id: `00000000-0000-4000-8000-${String(id).padStart(12, "0")}`,
    program_day_id: null,
    program_day_name: null,
    started_at: started,
    ended_at: null,
    notes: "",
    set_count: 1,
    exercise_count: 1,
    volume_kg: volume,
  });

  it("count this ISO week's sessions and volume", () => {
    const items = [w(3, "2026-10-18T17:00:00Z", 1000.5), w(2, "2026-10-12T06:00:00Z", 2000), w(1, "2026-10-11T23:59:00Z", 5000)];
    expect(gymWeek(items, "2026-10-18")).toEqual({ sessions: 2, volumeKg: 3000.5 });
  });

  it("show the gym week and today's intake from the API", async () => {
    vi.spyOn(trainingApi, "workouts").mockResolvedValue({ items: [w(3, "2026-10-18T17:00:00Z", 4120)], next_cursor: null });
    vi.spyOn(nutritionApi, "summary").mockResolvedValue(daySummary());
    render(await TrainingTilesBlock({ now: new Date("2026-10-18T20:00:00Z") }));
    expect(nutritionApi.summary).toHaveBeenCalledWith("2026-10-18");
    expect(screen.getByTestId("tile-gym")).toHaveTextContent("1 session");
    expect(screen.getByTestId("tile-gym")).toHaveTextContent("4,120 kg lifted");
    expect(screen.getByTestId("tile-intake")).toHaveTextContent("1,890 kcal");
    expect(screen.getByTestId("tile-intake")).toHaveTextContent("6 entries · target 2,400 kcal");
  });

  it("degrade per tile when a call fails", async () => {
    vi.spyOn(trainingApi, "workouts").mockRejectedValue(new ApiError(502, "down"));
    vi.spyOn(nutritionApi, "summary").mockResolvedValue(daySummary());
    render(await TrainingTilesBlock({ now: new Date("2026-10-18T20:00:00Z") }));
    expect(screen.getByTestId("tile-gym")).toHaveTextContent("could not load workouts");
    expect(screen.getByTestId("tile-intake")).toHaveTextContent("1,890 kcal");
  });
});
