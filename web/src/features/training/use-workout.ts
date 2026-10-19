"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SET_DONE_VIBRATION_MS, primeAudio, vibrate } from "@/features/training/alerts";
import { enqueue, flushQueue, isRetryable, readQueue } from "@/features/training/retry-queue";
import {
  type KeyValueStore,
  type Now,
  type RestTimer,
  type SetDraft,
  type WorkoutLocalState,
  clearWorkoutState,
  loadWorkoutState,
  saveWorkoutState,
  startRest,
} from "@/features/training/timers";
import type { Exercise, WorkoutDetail } from "@/features/training/types";
import {
  type ExerciseGroup,
  DEFAULT_REST_S,
  buildRows,
  extraRow,
  groupRows,
  parseSet,
  setBody,
  setPath,
} from "@/features/training/workout-rows";
import type { MutationResult } from "@/lib/mutate";

export type Send = (path: string, body: unknown) => Promise<MutationResult<unknown>>;
export type Finish = (workoutId: number) => Promise<MutationResult<WorkoutDetail>>;

/** Why finishing did not work: sets still in the retry queue, or the API's answer (status). */
export type FinishError = { kind: "pending"; count: number } | { kind: "failed"; status: number };

export interface WorkoutOptions {
  initial: WorkoutDetail;
  exercises: Exercise[];
  now: Now;
  store: KeyValueStore | null;
  send: Send;
  finish: Finish;
  newId: () => string;
  /** The rest label for a set, in the user's language ("Bench Press · set 2"). */
  restLabel: (exercise: string, setIndex: number) => string;
}

/**
 * The active workout's state (P6.6): rows with per-row client ids, optimistic idempotent PUTs,
 * the retry queue, the rest timer and finishing. Everything persists to localStorage until the
 * workout is finished, so a reload or a locked phone loses nothing.
 */
export function useWorkout({ initial, exercises, now, store, send, finish, newId, restLabel }: WorkoutOptions) {
  const workoutId = initial.id;
  const exerciseMap = useMemo(() => new Map(exercises.map((e) => [e.id, e])), [exercises]);
  const [local, setLocal] = useState<WorkoutLocalState>(() => {
    const saved = loadWorkoutState(store, workoutId);
    return {
      version: 1,
      workoutId,
      rest: saved?.rest ?? null,
      rows: buildRows(initial, saved, newId),
      extraExercises: saved?.extraExercises ?? [],
    };
  });
  const [summary, setSummary] = useState<WorkoutDetail | null>(null);
  const [finishing, setFinishing] = useState(false);
  const [finishError, setFinishError] = useState<FinishError | null>(null);
  const [queued, setQueued] = useState(() => readQueue(store).length);
  const inFlight = useRef(new Set<string>());

  useEffect(() => {
    if (!summary) saveWorkoutState(store, local);
  }, [local, store, summary]);

  const updateRow = useCallback((clientId: string, change: Partial<SetDraft>) => {
    setLocal((s) => ({ ...s, rows: s.rows.map((r) => (r.clientId === clientId ? { ...r, ...change } : r)) }));
  }, []);

  const applyFlush = useCallback(async () => {
    const result = await flushQueue(store, send);
    setLocal((s) => ({
      ...s,
      rows: s.rows.map((r) => {
        const path = setPath(workoutId, r.clientId);
        if (result.sent.includes(path)) return { ...r, status: "saved", error: undefined };
        return result.dropped.some((d) => d.path === path) ? { ...r, status: "error", error: "rejected" } : r;
      }),
    }));
    setQueued(result.remaining);
    return result;
  }, [send, store, workoutId]);

  useEffect(() => {
    const onOnline = () => void applyFlush();
    window.addEventListener("online", onOnline);
    // Sets queued before a reload go out as soon as the page is back.
    const initialFlush = setTimeout(() => {
      if (readQueue(store).length > 0) void applyFlush();
    }, 0);
    return () => {
      clearTimeout(initialFlush);
      window.removeEventListener("online", onOnline);
    };
  }, [applyFlush, store]);

  const groups = groupRows(initial, local.rows, local.extraExercises, exerciseMap);

  async function logSet(group: ExerciseGroup, row: SetDraft) {
    // A second tap while the first is on its way is ignored: one request, one client id.
    if (inFlight.current.has(row.clientId)) return;
    const parsed = parseSet(row.reps, row.weightKg);
    if (!parsed.ok) {
      updateRow(row.clientId, { status: "error", error: parsed.error });
      return;
    }
    const correction = row.status === "saved";
    primeAudio();
    vibrate(SET_DONE_VIBRATION_MS);
    const t = now();
    const completedAt = row.completedAt ?? new Date(t).toISOString();
    const path = setPath(workoutId, row.clientId);
    const body = setBody(row, parsed, completedAt, group.restSeconds);
    inFlight.current.add(row.clientId);
    setLocal((s) => ({
      ...s,
      rows: s.rows.map((r) => {
        if (r.clientId === row.clientId) return { ...r, completedAt, status: "saving", error: undefined };
        // Later empty sets of the same exercise take this set's numbers as their starting point.
        if (r.exerciseId === row.exerciseId && r.setIndex > row.setIndex && r.status === "idle") {
          return { ...r, reps: r.reps || row.reps, weightKg: r.weightKg || row.weightKg };
        }
        return r;
      }),
      rest: correction ? s.rest : startRest(t, group.restSeconds, restLabel(group.name, row.setIndex)),
    }));
    const result = await send(path, body);
    inFlight.current.delete(row.clientId);
    if (result.ok) {
      updateRow(row.clientId, { status: "saved", error: undefined });
      if (readQueue(store).length > 0) void applyFlush();
    } else if (isRetryable(result.status)) {
      enqueue(store, { path, body, queuedAt: now() });
      setQueued(readQueue(store).length);
      updateRow(row.clientId, { status: "queued", error: undefined });
    } else {
      updateRow(row.clientId, { status: "error", error: "rejected" });
    }
  }

  const updateRest = useCallback((update: (rest: RestTimer) => RestTimer | null) => {
    setLocal((s) => (s.rest ? { ...s, rest: update(s.rest) } : s));
  }, []);

  function addSet(group: ExerciseGroup) {
    setLocal((s) => ({ ...s, rows: [...s.rows, extraRow(group, newId)] }));
  }

  function addExercise(exercise: Exercise) {
    setLocal((s) => {
      if (s.extraExercises.some((e) => e.id === exercise.id) || initial.planned.some((p) => p.exercise.id === exercise.id)) return s;
      const extra = { id: exercise.id, name: exercise.name, equipment: exercise.equipment, restSeconds: DEFAULT_REST_S };
      const group: ExerciseGroup = { exerciseId: exercise.id, name: exercise.name, equipment: exercise.equipment, restSeconds: DEFAULT_REST_S, planned: null, rows: [] };
      return { ...s, extraExercises: [...s.extraExercises, extra], rows: [...s.rows, extraRow(group, newId)] };
    });
  }

  async function onFinish() {
    setFinishing(true);
    setFinishError(null);
    const pending = readQueue(store).filter((e) => e.path.startsWith(`/v1/training/workouts/${workoutId}/`));
    if (pending.length > 0) {
      const flushed = await applyFlush();
      if (flushed.remaining > 0) {
        setFinishing(false);
        setFinishError({ kind: "pending", count: flushed.remaining });
        return;
      }
    }
    const result = await finish(workoutId);
    setFinishing(false);
    if (!result.ok || !result.data) {
      setFinishError({ kind: "failed", status: result.status });
      return;
    }
    clearWorkoutState(store, workoutId);
    setSummary(result.data);
  }

  return { local, groups, queued, summary, finishing, finishError, updateRow, logSet, updateRest, addSet, addExercise, onFinish };
}
