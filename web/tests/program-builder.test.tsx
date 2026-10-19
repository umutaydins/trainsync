import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProgramBuilder } from "@/features/training/components/program-builder";
import { CSRF_COOKIE } from "@/lib/csrf-cookie";
import { fromPreview, move, toProgramIn } from "@/features/training/program-draft";
import type { ProgramSummary } from "@/features/training/types";
import { jsonResponse } from "./support/env";
import { renderWithIntl as render } from "./support/intl";
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
      { key: "repsOrder", day: 1, name: "Bench Press" },
      { key: "sets", day: 1, name: "Dumbbell Curl" },
      { key: "weight", day: 1, name: "Dumbbell Curl" },
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

  it("says when the generator refuses, in the user's words, not the API's", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ error: "upper_lower takes 4 days a week", detail: "upper_lower takes 4 days a week" }, 400));
    render(<ProgramBuilder initial={[]} exercises={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Generate preview" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The generator cannot build this combination.");
    expect(alert).not.toHaveTextContent("upper_lower");
  });

  it("names the fields the API would refuse before saving, in Turkish too", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(PREVIEW));
    render(<ProgramBuilder initial={[]} exercises={[BENCH, CURL]} />, "tr");
    fireEvent.click(screen.getByRole("button", { name: "Önizleme oluştur" }));
    await screen.findByTestId("program-editor");
    fireEvent.change(screen.getByLabelText("Set, Bench Press"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Programı kaydet" }));
    expect(screen.getByRole("alert")).toHaveTextContent("1. gün, Bench Press: set 1 ile 10 arası");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("checks the minutes per session before asking the API", () => {
    render(<ProgramBuilder initial={[]} exercises={[]} />);
    fireEvent.change(screen.getByLabelText("Minutes per session"), { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Generate preview" }));
    expect(screen.getByText("Minutes per session: 20 to 180.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
