import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WorkoutScreen } from "@/features/training/components/workout-screen";
import type { MutationResult } from "@/lib/mutate";
import { readQueue } from "@/features/training/retry-queue";
import type { KeyValueStore } from "@/features/training/timers";
import type { WorkoutDetail } from "@/features/training/types";
import { jsonResponse } from "./support/env";
import { BENCH, CURL, PLATES_100, idSequence, memoryStore, planned, workout } from "./support/training-fixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/training" }));

const T0 = Date.parse("2026-10-18T17:30:00Z");
type Send = (path: string, body: unknown) => Promise<MutationResult<unknown>>;

const ok = (data: unknown = null): MutationResult<unknown> => ({ ok: true, status: 201, data });

function setup(options: { send?: Send; store?: KeyValueStore; initial?: WorkoutDetail; finish?: () => Promise<MutationResult<WorkoutDetail>> } = {}) {
  const send = vi.fn<Send>(options.send ?? (() => Promise.resolve(ok())));
  const store = options.store ?? memoryStore();
  const finish = vi.fn(options.finish ?? (() => Promise.resolve({ ok: true as const, status: 200, data: workout() })));
  const view = render(
    <WorkoutScreen initial={options.initial ?? workout()} exercises={[BENCH, CURL]} store={store} send={send} finish={finish} newId={idSequence()} />,
  );
  return { send, store, finish, view };
}

function rows() {
  return screen.getAllByTestId("set-row");
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(T0 + 5 * 60_000); // five minutes into the workout
});

afterEach(() => {
  vi.useRealTimers();
});

describe("workout screen", () => {
  it("shows planned sets with last time and the suggested weight", () => {
    setup();
    expect(screen.getByRole("heading", { name: "Bench Press" })).toBeInTheDocument();
    expect(rows()).toHaveLength(5); // 3 bench + 2 curl
    const bench = rows()[0]!;
    expect(within(bench).getByLabelText("Weight in kg, Bench Press set 1")).toHaveValue("80");
    expect(within(bench).getByLabelText("Reps, Bench Press set 1")).toHaveValue("8");
    expect(bench).toHaveTextContent("Last: 12 × 77.5 kg");
    expect(screen.getAllByTestId("suggestion")[0]).toHaveTextContent("Suggested 80 kg");
    expect(screen.getByTestId("workout-elapsed")).toHaveTextContent("5:00");
  });

  it("a double tap sends one PUT with one client id", async () => {
    let answer: (value: MutationResult<unknown>) => void = () => undefined;
    const { send } = setup({ send: () => new Promise((resolve) => (answer = resolve)) });
    const button = screen.getByRole("button", { name: "Log Bench Press set 1" });
    const clientId = rows()[0]!.getAttribute("data-client-id");

    fireEvent.click(button);
    fireEvent.click(button);
    expect(send).toHaveBeenCalledTimes(1);
    const [path, body] = send.mock.calls[0]!;
    expect(path).toBe(`/v1/training/workouts/42/sets/${clientId}`);
    expect(body).toEqual({
      exercise_id: 20,
      set_index: 1,
      reps: 8,
      weight_kg: 80,
      is_warmup: false,
      completed_at: new Date(T0 + 5 * 60_000).toISOString(),
      rest_seconds: 90,
    });
    expect(rows()[0]).toHaveAttribute("data-status", "saving");

    await act(async () => answer(ok()));
    expect(rows()[0]).toHaveAttribute("data-status", "saved");
    expect(screen.getByRole("button", { name: "Update Bench Press set 1" })).toBeInTheDocument();
  });

  it("starts the rest timer after a set and keeps it right when the tab was backgrounded", async () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Log Bench Press set 1" }));
    await flush();
    expect(screen.getByTestId("rest-remaining")).toHaveTextContent("1:30");

    act(() => vi.advanceTimersByTime(10_000));
    expect(screen.getByTestId("rest-remaining")).toHaveTextContent("1:20");

    // Backgrounded for 3 minutes: the wall clock moves, no interval runs.
    vi.setSystemTime(Date.now() + 180_000);
    expect(screen.getByTestId("rest-remaining")).toHaveTextContent("1:20");
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(screen.getByTestId("rest-remaining")).toHaveTextContent("0:00");
    expect(screen.getByTestId("rest-timer")).toHaveTextContent("Rest over");
    expect(screen.getByTestId("workout-elapsed")).toHaveTextContent("8:10");

    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByTestId("rest-timer")).not.toBeInTheDocument();
  });

  it("+15 s, -15 s and skip", async () => {
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Log Dumbbell Curl set 1" }));
    await flush();
    expect(screen.getByTestId("rest-remaining")).toHaveTextContent("1:00");
    fireEvent.click(screen.getByRole("button", { name: "+15 s rest" }));
    expect(screen.getByTestId("rest-remaining")).toHaveTextContent("1:15");
    fireEvent.click(screen.getByRole("button", { name: "−15 s rest" }));
    fireEvent.click(screen.getByRole("button", { name: "−15 s rest" }));
    expect(screen.getByTestId("rest-remaining")).toHaveTextContent("0:45");
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(screen.queryByTestId("rest-timer")).not.toBeInTheDocument();
  });

  it("vibrates at zero", async () => {
    const vibrate = vi.fn();
    Object.defineProperty(navigator, "vibrate", { value: vibrate, configurable: true });
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Log Dumbbell Curl set 1" }));
    await flush();
    act(() => vi.advanceTimersByTime(59_000));
    expect(vibrate).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1_500));
    expect(vibrate).toHaveBeenCalledTimes(1);
    act(() => vi.advanceTimersByTime(5_000));
    expect(vibrate).toHaveBeenCalledTimes(1);
    Reflect.deleteProperty(navigator, "vibrate");
  });

  it("restores the rest timer and the row ids after a reload", async () => {
    const store = memoryStore();
    const first = setup({ store });
    const ids = rows().map((r) => r.getAttribute("data-client-id"));
    fireEvent.click(screen.getByRole("button", { name: "Log Bench Press set 1" }));
    await flush();
    first.view.unmount();

    vi.setSystemTime(Date.now() + 40_000);
    const logged = first.send.mock.calls[0]![1] as { completed_at: string };
    setup({
      store,
      initial: workout({
        sets: [
          {
            client_id: ids[0]!,
            workout_id: 42,
            exercise_id: 20,
            set_index: 1,
            reps: 8,
            weight_kg: 80,
            rpe: null,
            is_warmup: false,
            completed_at: logged.completed_at,
            rest_seconds: 90,
          },
        ],
      }),
    });
    expect(rows().map((r) => r.getAttribute("data-client-id"))).toEqual(ids);
    expect(rows()[0]).toHaveAttribute("data-status", "saved");
    expect(screen.getByTestId("rest-remaining")).toHaveTextContent("0:50");
  });

  it("queues a set that got no answer and sends it again, same id, when back online", async () => {
    const answers: MutationResult<unknown>[] = [{ ok: false, status: 0, error: "network error" }, ok()];
    const { send, store } = setup({ send: () => Promise.resolve(answers.shift() ?? ok()) });
    fireEvent.click(screen.getByRole("button", { name: "Log Bench Press set 1" }));
    await flush();
    expect(rows()[0]).toHaveAttribute("data-status", "queued");
    expect(rows()[0]).toHaveTextContent("Saved on this phone, will retry");
    const [path, body] = send.mock.calls[0]!;
    expect(readQueue(store)).toEqual([{ path, body, queuedAt: expect.any(Number) }]);
    expect(screen.getByTestId("queued-count")).toHaveTextContent("1 waiting to sync");

    await act(async () => {
      window.dispatchEvent(new Event("online"));
    });
    await flush();
    expect(send).toHaveBeenCalledTimes(2);
    expect(send.mock.calls[1]).toEqual([path, body]);
    expect(rows()[0]).toHaveAttribute("data-status", "saved");
    expect(readQueue(store)).toEqual([]);
  });

  it("shows a rejected set as an error, not queued", async () => {
    const { store } = setup({ send: () => Promise.resolve({ ok: false, status: 422, error: "invalid set" }) });
    fireEvent.click(screen.getByRole("button", { name: "Log Bench Press set 1" }));
    await flush();
    expect(rows()[0]).toHaveAttribute("data-status", "error");
    expect(rows()[0]).toHaveTextContent("invalid set");
    expect(readQueue(store)).toEqual([]);
  });

  it("checks the numbers before sending", async () => {
    const { send } = setup();
    fireEvent.change(screen.getByLabelText("Weight in kg, Bench Press set 1"), { target: { value: "80.3" } });
    fireEvent.click(screen.getByRole("button", { name: "Log Bench Press set 1" }));
    expect(send).not.toHaveBeenCalled();
    expect(rows()[0]).toHaveTextContent("0.25 kg steps");
    fireEvent.change(screen.getByLabelText("Weight in kg, Bench Press set 1"), { target: { value: "82,5" } });
    fireEvent.click(screen.getByRole("button", { name: "Log Bench Press set 1" }));
    expect(send.mock.calls[0]![1]).toMatchObject({ weight_kg: 82.5 });
  });

  it("a logged weight fills the later empty sets of that exercise", async () => {
    const fresh = planned(BENCH, { suggestion: { action: "start", weight_kg: null, previous_weight_kg: null }, start_weight_kg: null, last_performance: null });
    setup({ initial: workout({ planned: [fresh] }) });
    expect(screen.getByLabelText("Weight in kg, Bench Press set 2")).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Plates" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Weight in kg, Bench Press set 1"), { target: { value: "50" } });
    fireEvent.click(screen.getByRole("button", { name: "Log Bench Press set 1" }));
    await flush();
    expect(screen.getByLabelText("Weight in kg, Bench Press set 2")).toHaveValue("50");
    expect(screen.getByLabelText("Weight in kg, Bench Press set 3")).toHaveValue("50");
    expect(screen.getByRole("button", { name: "Plates" })).toBeInTheDocument();
  });

  it("adds a set and an exercise", async () => {
    setup();
    fireEvent.click(screen.getAllByRole("button", { name: "Add set" })[1]!);
    expect(rows()).toHaveLength(6);
    expect(screen.getByLabelText("Weight in kg, Dumbbell Curl set 3")).toHaveValue("12.5");
  });

  it("opens the plate calculator with the API's answer", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(PLATES_100));
    vi.stubGlobal("fetch", fetchMock);
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Plates" }));
    await flush();
    await flush();
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/ts/v1/training/plates?target=80");
    const dialog = screen.getByRole("dialog", { name: "Plates for 80 kg" });
    expect(within(dialog).getByTestId("plates-per-side")).toHaveTextContent("25 + 15");
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("finishes: flushes the queue first, then shows the summary", async () => {
    const done = workout({
      ended_at: "2026-10-18T18:35:00Z",
      volume_kg: 1920,
      set_count: 3,
      records: [{ exercise_id: 20, exercise_name: "Bench Press", kind: "weight_for_reps", value: 80, previous: 77.5, reps: 8 }],
    });
    const { finish, store } = setup({ finish: () => Promise.resolve({ ok: true, status: 200, data: done }) });
    fireEvent.click(screen.getByRole("button", { name: "Finish workout" }));
    await flush();
    expect(finish).toHaveBeenCalledWith(42);
    const summary = screen.getByTestId("workout-summary");
    expect(summary).toHaveTextContent("1:05:00");
    expect(summary).toHaveTextContent("1,920 kg");
    expect(within(screen.getByTestId("workout-records")).getByText("80 kg × 8")).toBeInTheDocument();
    expect(store.getItem("trainsync.workout.42")).toBeNull();
  });

  it("does not finish while sets are still waiting", async () => {
    const { finish } = setup({ send: () => Promise.resolve({ ok: false, status: 0, error: "network error" }) });
    fireEvent.click(screen.getByRole("button", { name: "Log Bench Press set 1" }));
    await flush();
    fireEvent.click(screen.getByRole("button", { name: "Finish workout" }));
    await flush();
    expect(finish).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("1 set is still waiting to be saved");
  });
});
