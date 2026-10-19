import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  LATE_ALERT_MS,
  adjustRest,
  elapsedMs,
  isFinished,
  loadWorkoutState,
  remainingSeconds,
  restProgress,
  saveWorkoutState,
  shouldAlert,
  startRest,
  storageKey,
} from "@/features/training/timers";
import { memoryStore } from "./support/training-fixtures";

const T0 = Date.parse("2026-10-18T17:30:00Z");

describe("rest timer (timestamp-based)", () => {
  it("counts down from endsAt - now", () => {
    const rest = startRest(T0, 90, "Bench Press · set 1");
    expect(rest.endsAt).toBe(T0 + 90_000);
    expect(remainingSeconds(rest, T0)).toBe(90);
    expect(remainingSeconds(rest, T0 + 400)).toBe(90); // rounds up: 89.6 s left shows 1:30
    expect(remainingSeconds(rest, T0 + 30_000)).toBe(60);
    expect(remainingSeconds(rest, T0 + 90_000)).toBe(0);
    expect(remainingSeconds(rest, T0 + 500_000)).toBe(0);
    expect(isFinished(rest, T0 + 89_999)).toBe(false);
    expect(isFinished(rest, T0 + 90_000)).toBe(true);
    expect(restProgress(rest, T0 + 45_000)).toBeCloseTo(0.5);
  });

  it("+15 s / -15 s move endsAt, never before now", () => {
    const rest = startRest(T0, 90, "x");
    expect(adjustRest(rest, 15, T0).endsAt).toBe(T0 + 105_000);
    expect(adjustRest(rest, -15, T0).endsAt).toBe(T0 + 75_000);
    expect(adjustRest(rest, -15, T0 + 85_000).endsAt).toBe(T0 + 85_000);
    // Extending a finished rest starts again from now and re-arms the alert.
    const over = { ...rest, alerted: true };
    const again = adjustRest(over, 15, T0 + 200_000);
    expect(again.endsAt).toBe(T0 + 215_000);
    expect(again.alerted).toBe(false);
  });

  it("alerts once at zero, and not when the tab slept far past it", () => {
    const rest = startRest(T0, 60, "x");
    expect(shouldAlert(rest, T0 + 59_000)).toBe(false);
    expect(shouldAlert(rest, T0 + 60_000)).toBe(true);
    expect(shouldAlert({ ...rest, alerted: true }, T0 + 60_000)).toBe(false);
    expect(shouldAlert(rest, T0 + 60_000 + LATE_ALERT_MS + 1)).toBe(false);
  });

  it("workout time is now - startedAt", () => {
    expect(elapsedMs(T0, T0 + 65_000)).toBe(65_000);
    expect(elapsedMs(T0, T0 - 1000)).toBe(0);
  });
});

describe("with fake timers", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(T0);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("stays correct after the tab is backgrounded for 3 minutes (no interval ticks)", () => {
    const rest = startRest(Date.now(), 120, "Squat · set 2");
    const rendered: number[] = [];
    const interval = setInterval(() => rendered.push(remainingSeconds(rest, Date.now())), 1000);
    vi.advanceTimersByTime(3000);
    expect(rendered).toEqual([119, 118, 117]);

    // Backgrounded: the browser freezes the interval, but the wall clock moves on.
    vi.setSystemTime(T0 + 3000 + 180_000);
    expect(rendered).toHaveLength(3);
    expect(remainingSeconds(rest, Date.now())).toBe(0);
    expect(isFinished(rest, Date.now())).toBe(true);
    expect(elapsedMs(T0, Date.now())).toBe(183_000);
    clearInterval(interval);
  });

  it("restores the timer after a reload from localStorage", () => {
    const store = memoryStore();
    const rest = startRest(Date.now(), 90, "Bench Press · set 1");
    saveWorkoutState(store, { version: 1, workoutId: 42, rest, rows: [], extraExercises: [] });

    vi.advanceTimersByTime(40_000); // the page reloads 40 s later
    const restored = loadWorkoutState(store, 42);
    expect(restored?.rest).toEqual(rest);
    expect(remainingSeconds(restored!.rest!, Date.now())).toBe(50);
  });

  it("ignores state of another workout or a broken entry", () => {
    const store = memoryStore();
    store.setItem(storageKey(7), "{not json");
    expect(loadWorkoutState(store, 7)).toBeNull();
    store.setItem(storageKey(8), JSON.stringify({ version: 1, workoutId: 9, rows: [] }));
    expect(loadWorkoutState(store, 8)).toBeNull();
    expect(loadWorkoutState(null, 8)).toBeNull();
  });

  it("survives storage that throws", () => {
    const throwing = {
      getItem: () => {
        throw new Error("denied");
      },
      setItem: () => {
        throw new Error("quota");
      },
      removeItem: () => undefined,
    };
    expect(() => saveWorkoutState(throwing, { version: 1, workoutId: 1, rest: null, rows: [], extraExercises: [] })).not.toThrow();
    expect(loadWorkoutState(throwing, 1)).toBeNull();
  });
});
