import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProgramBuilder } from "@/components/training/program-builder";
import { CSRF_COOKIE } from "@/lib/csrf-cookie";
import { fromPreview, move, toProgramIn } from "@/lib/program-draft";
import type { ProgramSummary } from "@/lib/training-types";
import { jsonResponse } from "./support/env";
import { BENCH, CURL, PREVIEW } from "./support/training-fixtures";

const fetchMock = vi.fn<typeof fetch>();

const SAVED: ProgramSummary = {
  id: 3,
  name: "Upper/Lower hypertrophy",
  goal: "hypertrophy",
  days_per_week: 2,
  weeks: 8,
  active: false,
  created_at: "2026-10-18T10:00:00Z",
};

function calls() {
  return fetchMock.mock.calls.map(([url, init]) => ({
    url: String(url),
    method: init?.method ?? "GET",
    body: init?.body ? JSON.parse(String(init.body)) : undefined,
  }));
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  document.cookie = `${CSRF_COOKIE}=${"t".repeat(43)}`;
});

describe("program draft", () => {
  it("round-trips the generated program unchanged", () => {
    const checked = toProgramIn(fromPreview(PREVIEW));
    expect(checked).toEqual({ ok: true, body: { ...PREVIEW.program } });
  });

  it("moves items and reports bad numbers", () => {
    expect(move([1, 2, 3], 0, 1)).toEqual([2, 1, 3]);
    expect(move([1, 2, 3], 0, -1)).toEqual([1, 2, 3]);
    const draft = fromPreview(PREVIEW);
    draft.days[0]!.exercises[0]!.repMin = "13";
    draft.days[0]!.exercises[1]!.sets = "0";
    draft.days[0]!.exercises[1]!.startWeightKg = "20.1";
    const checked = toProgramIn(draft);
    expect(checked.ok).toBe(false);
    expect(!checked.ok && checked.errors).toEqual([
      "Day 1, Bench Press: minimum reps above maximum",
      "Day 1, Dumbbell Curl: sets 1 to 10",
      "Day 1, Dumbbell Curl: start weight 0 to 500 kg in 0.25 steps",
    ]);
  });
});

describe("program builder", () => {
  it("generates a preview, edits it, saves and activates", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(PREVIEW)) // generate
      .mockResolvedValueOnce(jsonResponse({ ...SAVED, days: [] }, 201)) // save
      .mockResolvedValueOnce(jsonResponse({ items: [SAVED] })) // refresh
      .mockResolvedValueOnce(jsonResponse({ ...SAVED, active: true, days: [] })) // activate
      .mockResolvedValueOnce(jsonResponse({ items: [{ ...SAVED, active: true }] })); // refresh
    render(<ProgramBuilder initial={[]} exercises={[BENCH, CURL]} />);

    fireEvent.change(screen.getByLabelText("Days per week"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Machine" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate preview" }));
    const editor = await screen.findByTestId("program-editor");
    expect(calls()[0]).toEqual({
      url: "/api/ts/v1/training/programs/generate",
      method: "POST",
      body: { days_per_week: 4, goal: "hypertrophy", equipment: ["barbell", "dumbbell", "machine"], session_minutes: 60, weeks: 8 },
    });
    expect(within(editor).getAllByTestId("editor-day")).toHaveLength(2);
    expect(editor).toHaveTextContent("about 53 min");

    // Reorder: curl first, then 4 sets → 5.
    fireEvent.click(screen.getByRole("button", { name: "Move Dumbbell Curl up" }));
    fireEvent.change(screen.getByLabelText("Sets, Bench Press"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save program" }));
    await screen.findByText("Saved “Upper/Lower hypertrophy”.");
    const saved = calls()[1]!;
    expect(saved.url).toBe("/api/ts/v1/training/programs");
    expect(saved.method).toBe("POST");
    expect(saved.body.days[0].exercises.map((e: { exercise_id: number; sets: number }) => [e.exercise_id, e.sets])).toEqual([
      [31, 3],
      [20, 5],
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Activate it" }));
    await screen.findByText("Program activated. Start a day from Today.");
    expect(calls()[3]).toMatchObject({ url: "/api/ts/v1/training/programs/3/activate", method: "POST" });
    await waitFor(() => expect(within(screen.getByTestId("program-list")).getByText("Active")).toBeInTheDocument());
  });

  it("shows the API's reason when generating fails", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ error: "upper_lower takes 4 days a week", detail: "upper_lower takes 4 days a week" }, 400));
    render(<ProgramBuilder initial={[]} exercises={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Generate preview" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("upper_lower takes 4 days a week");
  });
});
