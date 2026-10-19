import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RestTimerPanel } from "@/features/training/components/rest-timer";
import { WorkoutScreen } from "@/features/training/components/workout-screen";
import { DEFAULT_WEIGHT_STEP_KG, stepped, weightStep } from "@/features/training/steps";
import { startRest } from "@/features/training/timers";
import type { MutationResult } from "@/lib/mutate";
import { violations } from "./support/axe";
import { jsonResponse } from "./support/env";
import { renderWithIntl } from "./support/intl";
import { BENCH, CURL, PLATES_100, idSequence, memoryStore, workout } from "./support/training-fixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/training/workout/42" }));

const T0 = Date.parse("2026-10-18T17:30:00Z");
type Send = (path: string, body: unknown) => Promise<MutationResult<unknown>>;

function stubScreen(desktop: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: desktop && query.includes("min-width"),
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

function setup(locale: "en" | "tr" = "en") {
  const send = vi.fn<Send>(() => Promise.resolve({ ok: true, status: 201, data: null }));
  renderWithIntl(<WorkoutScreen initial={workout()} exercises={[BENCH, CURL]} store={memoryStore()} send={send} newId={idSequence()} />, locale);
  return send;
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

beforeEach(() => {
  stubScreen(true);
  vi.useFakeTimers();
  vi.setSystemTime(T0 + 60_000);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("steppers", () => {
  it("step by the equipment's increment, on the API's grid, within bounds", () => {
    expect(weightStep("barbell")).toBe(DEFAULT_WEIGHT_STEP_KG);
    expect(weightStep("kettlebell")).toBe(4);
    const kg = { min: 0, max: 500, grid: 0.25 };
    expect(stepped("80", 2.5, kg)).toBe("82.5");
    expect(stepped("80,3", 2.5, kg)).toBe("82.75");
    expect(stepped("", -2.5, kg)).toBe("0");
    expect(stepped("499", 2.5, kg)).toBe("500");
    expect(stepped("8", -1, { min: 0, max: 100, grid: 1 })).toBe("7");
  });

  it("only the next set is big; its +/− buttons are 64 px and move weight and reps", async () => {
    const send = setup();
    const more = screen.getByRole("button", { name: "More weight, Bench Press set 1" });
    expect(more).toHaveClass("size-16");
    expect(screen.queryByRole("button", { name: "More weight, Bench Press set 2" })).not.toBeInTheDocument();
    fireEvent.click(more);
    expect(screen.getByLabelText("Weight in kg, Bench Press set 1")).toHaveValue("82.5");
    fireEvent.click(screen.getByRole("button", { name: "Fewer reps, Bench Press set 1" }));
    expect(screen.getByLabelText("Reps, Bench Press set 1")).toHaveValue("7");

    // One tap: "Set done" logs the set with the stepped numbers and the next set becomes the big one.
    fireEvent.click(screen.getByRole("button", { name: "Log Bench Press set 1" }));
    await flush();
    expect(send.mock.calls[0]![1]).toMatchObject({ reps: 7, weight_kg: 82.5 });
    fireEvent.click(screen.getByRole("button", { name: "Hide timer" }));
    expect(screen.getByRole("button", { name: "More weight, Bench Press set 2" })).toBeInTheDocument();
    expect(screen.getByLabelText("Weight in kg, Bench Press set 2")).toHaveValue("80");
    expect(screen.getByRole("button", { name: "Update Bench Press set 1" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("rest timer", () => {
  it("is full screen with a ring and big figures, hides to a bar and comes back", async () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Log Bench Press set 1" }));
    await flush();
    const timer = screen.getByRole("dialog", { name: "Rest" });
    expect(timer).toHaveAttribute("data-testid", "rest-timer");
    expect(within(timer).getByRole("progressbar", { name: "Rest so far" })).toHaveAttribute("aria-valuenow", "0");
    expect(within(timer).getByText("After Bench Press · set 1")).toBeInTheDocument();
    expect(within(timer).getByRole("button", { name: "Skip" })).toHaveFocus();

    act(() => vi.advanceTimersByTime(45_000));
    expect(within(timer).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");

    fireEvent.click(within(timer).getByRole("button", { name: "Hide timer" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const bar = screen.getByRole("region", { name: "Rest" });
    expect(within(bar).getByTestId("rest-remaining")).toHaveTextContent("0:45");
    fireEvent.click(within(bar).getByRole("button", { name: "Show the rest timer" }));
    expect(screen.getByRole("dialog", { name: "Rest" })).toBeInTheDocument();
  });

  it("a new set opens a hidden timer full screen again", async () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Log Bench Press set 1" }));
    await flush();
    fireEvent.click(screen.getByRole("button", { name: "Hide timer" }));
    fireEvent.click(screen.getByRole("button", { name: "Log Bench Press set 2" }));
    await flush();
    expect(screen.getByRole("dialog", { name: "Rest" })).toHaveTextContent("After Bench Press · set 2");
  });

  it("has no axe violations, in English and Turkish", async () => {
    vi.useRealTimers();
    const rest = startRest(0, 90, "Bench Press · set 1");
    const panel = <RestTimerPanel rest={rest} now={30_000} onAdjust={() => undefined} onSkip={() => undefined} />;
    expect(await violations(panel)).toEqual([]);
    cleanup();
    expect(await violations(panel, "tr")).toEqual([]);
  });
});

describe("plate sheet", () => {
  it("is a bottom sheet on a phone with the API's plates and a Done button", async () => {
    stubScreen(false);
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(PLATES_100));
    vi.stubGlobal("fetch", fetchMock);
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Plates" }));
    await flush();
    await flush();
    const sheet = screen.getByRole("dialog", { name: "Plates for 80 kg" });
    expect(sheet).toHaveTextContent("Bench Press");
    expect(within(sheet).getByTestId("plates-per-side")).toHaveTextContent("25 + 15");
    expect(within(sheet).queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
    fireEvent.click(within(sheet).getByRole("button", { name: "Done" }));
    await flush();
    expect(screen.queryByRole("dialog", { name: "Plates for 80 kg" })).not.toBeInTheDocument();
  });

  it("says when the backend is down, in the user's language", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ error: "trainsync API unavailable" }, 502)));
    setup("tr");
    fireEvent.click(screen.getByRole("button", { name: "Plakalar" }));
    await flush();
    await flush();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Plakalar hesaplanamadı");
    expect(alert).not.toHaveTextContent("trainsync API unavailable");
  });
});

describe("workout screen in Turkish", () => {
  it("speaks Turkish and formats numbers the Turkish way", () => {
    setup("tr");
    expect(screen.getByRole("button", { name: "Bench Press 1. seti kaydet" })).toHaveTextContent("Set tamam");
    expect(screen.getAllByTestId("set-row")[0]).toHaveTextContent("Geçen sefer 12 × 77,5 kg");
    expect(screen.getByRole("button", { name: "Antrenmanı bitir" })).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    vi.useRealTimers();
    const ui = <WorkoutScreen initial={workout()} exercises={[BENCH, CURL]} store={memoryStore()} />;
    expect(await violations(ui)).toEqual([]);
    cleanup();
    expect(await violations(ui, "tr")).toEqual([]);
  });
});
