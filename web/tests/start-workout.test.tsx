import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StartWorkoutButton } from "@/features/training/components/start-workout";
import type { MutationResult } from "@/lib/mutate";
import type { WorkoutDetail } from "@/features/training/types";
import { idSequence, workout } from "./support/training-fixtures";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }), usePathname: () => "/training" }));

type Send = (path: string, body: unknown) => Promise<MutationResult<WorkoutDetail>>;

const started: MutationResult<WorkoutDetail> = { ok: true, status: 201, data: { ...workout(), id: 77 } };
const lost: MutationResult<WorkoutDetail> = { ok: false, status: 0, error: "Network error" };

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

beforeEach(() => push.mockReset());

describe("start workout", () => {
  it("a double tap sends one PUT under one client id", async () => {
    let answer: (value: MutationResult<WorkoutDetail>) => void = () => undefined;
    const send = vi.fn<Send>(() => new Promise((resolve) => (answer = resolve)));
    render(<StartWorkoutButton programDayId={11} label="Start Upper A" send={send} newId={idSequence()} />);
    const button = screen.getByRole("button", { name: "Start Upper A" });

    fireEvent.click(button);
    fireEvent.click(button);
    expect(send).toHaveBeenCalledTimes(1);
    const [path, body] = send.mock.calls[0]!;
    expect(path).toMatch(/^\/v1\/training\/workouts\/[0-9a-f-]{36}$/);
    expect(body).toEqual({ program_day_id: 11 });

    answer(started);
    await flush();
    expect(push).toHaveBeenCalledWith("/training/workout/77");
  });

  it("a retry after a lost answer reuses the client id, so the API returns the same workout", async () => {
    const answers = [lost, { ...started, status: 200 }];
    const send = vi.fn<Send>(() => Promise.resolve(answers.shift()!));
    render(<StartWorkoutButton label="Free workout" send={send} newId={idSequence()} />);

    fireEvent.click(screen.getByRole("button", { name: "Free workout" }));
    await flush();
    expect(screen.getByRole("alert")).toHaveTextContent("Network error. Tap again to retry.");
    expect(push).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Free workout" }));
    await flush();
    expect(send).toHaveBeenCalledTimes(2);
    expect(send.mock.calls[1]![0]).toBe(send.mock.calls[0]![0]);
    expect(send.mock.calls[0]![1]).toEqual({});
    expect(push).toHaveBeenCalledWith("/training/workout/77");
  });

  it("each button keeps its own id", async () => {
    const send = vi.fn<Send>(() => Promise.resolve(started));
    const newId = idSequence();
    render(
      <>
        <StartWorkoutButton programDayId={11} label="Start A" send={send} newId={newId} />
        <StartWorkoutButton programDayId={12} label="Start B" send={send} newId={newId} />
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Start A" }));
    fireEvent.click(screen.getByRole("button", { name: "Start B" }));
    await flush();
    expect(new Set(send.mock.calls.map(([path]) => path)).size).toBe(2);
  });
});
