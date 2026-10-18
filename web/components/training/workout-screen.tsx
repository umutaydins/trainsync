"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ExercisePicker } from "@/components/training/exercise-picker";
import { PlateSheet } from "@/components/training/plate-sheet";
import { RestTimerPanel } from "@/components/training/rest-timer";
import { WorkoutSummaryCard } from "@/components/training/workout-summary";
import { ErrorState, buttonClass, secondaryButtonClass } from "@/components/ui";
import { primeAudio, restOver } from "@/lib/alerts";
import { formatClock } from "@/lib/format";
import { type MutationResult, post, put } from "@/lib/mutate";
import { enqueue, flushQueue, isRetryable, readQueue } from "@/lib/retry-queue";
import {
  type KeyValueStore,
  type Now,
  type RestTimer,
  type SetDraft,
  type WorkoutLocalState,
  adjustRest,
  browserStorage,
  clearWorkoutState,
  elapsedMs,
  loadWorkoutState,
  saveWorkoutState,
  shouldAlert,
  startRest,
  systemNow,
} from "@/lib/timers";
import type { Exercise, WorkoutDetail } from "@/lib/training-types";
import { formatKg, formatVolume } from "@/lib/training-types";
import { useWakeLock } from "@/lib/wake-lock";
import {
  type ExerciseGroup,
  DEFAULT_REST_S,
  buildRows,
  extraRow,
  groupRows,
  loggedVolume,
  newClientId,
  parseSet,
  setBody,
  setPath,
} from "@/lib/workout-rows";

export const TICK_MS = 250;

type Send = (path: string, body: unknown) => Promise<MutationResult<unknown>>;

export interface WorkoutScreenProps {
  initial: WorkoutDetail;
  exercises: Exercise[];
  /** Test seams. */
  now?: Now;
  store?: KeyValueStore | null;
  send?: Send;
  finish?: (workoutId: number) => Promise<MutationResult<WorkoutDetail>>;
  newId?: () => string;
}

const defaultSend: Send = (path, body) => put<unknown>(path, body);
const defaultFinish = (id: number) => post<WorkoutDetail>(`/v1/training/workouts/${id}/finish`, {});

/**
 * The active-workout screen (P6.6): planned sets with last time and the suggested weight, two-tap
 * logging (optimistic, idempotent PUT with a per-row client id, retry queue), workout and rest
 * timers from timestamps, plate calculator, screen wake lock. Rendered on the client only.
 */
export function WorkoutScreen({
  initial,
  exercises,
  now = systemNow,
  store = browserStorage(),
  send = defaultSend,
  finish = defaultFinish,
  newId = newClientId,
}: WorkoutScreenProps) {
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
  const [clock, setClock] = useState(() => now());
  const [plates, setPlates] = useState<{ kg: number; name: string } | null>(null);
  const [picking, setPicking] = useState(false);
  const [summary, setSummary] = useState<WorkoutDetail | null>(null);
  const [finishing, setFinishing] = useState(false);
  const [finishError, setFinishError] = useState<string | null>(null);
  const [queued, setQueued] = useState(() => readQueue(store).length);

  const localRef = useRef(local);
  const inFlight = useRef(new Set<string>());
  // `endsAt` of the rest already signalled; the state update lands a render later than the next tick.
  const alertedAt = useRef<number | null>(null);
  useEffect(() => {
    localRef.current = local;
    if (!summary) saveWorkoutState(store, local);
  }, [local, store, summary]);

  const wakeLock = useWakeLock(summary === null);

  // ---------------------------------------------------------------- clock
  const tick = useCallback(() => {
    const t = now();
    setClock(t);
    const rest = localRef.current.rest;
    if (!rest || rest.alerted || alertedAt.current === rest.endsAt) return;
    if (shouldAlert(rest, t)) {
      alertedAt.current = rest.endsAt;
      restOver(rest.label);
      setLocal((s) => (s.rest ? { ...s, rest: { ...s.rest, alerted: true } } : s));
    } else if (t > rest.endsAt) {
      // Asleep through zero (more than a minute late): no alert, just mark it.
      alertedAt.current = rest.endsAt;
      setLocal((s) => (s.rest ? { ...s, rest: { ...s.rest, alerted: true } } : s));
    }
  }, [now]);

  useEffect(() => {
    const timer = setInterval(tick, TICK_MS);
    // Intervals are throttled or frozen in a background tab; re-render as soon as it is back.
    const onVisible = () => {
      if (document.visibilityState === "visible") tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", tick);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", tick);
    };
  }, [tick]);

  // ---------------------------------------------------------------- rows
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
        const dropped = result.dropped.find((d) => d.path === path);
        return dropped ? { ...r, status: "error", error: dropped.error } : r;
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
      rest: correction ? s.rest : startRest(t, group.restSeconds, `${group.name} · set ${row.setIndex}`),
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
      updateRow(row.clientId, { status: "error", error: result.error });
    }
  }

  function setRest(update: (rest: RestTimer, t: number) => RestTimer | null) {
    const t = now();
    setClock(t);
    setLocal((s) => (s.rest ? { ...s, rest: update(s.rest, t) } : s));
  }

  function addSet(group: ExerciseGroup) {
    setLocal((s) => ({ ...s, rows: [...s.rows, extraRow(group, newId)] }));
  }

  function addExercise(exercise: Exercise) {
    setPicking(false);
    setLocal((s) => {
      if (s.extraExercises.some((e) => e.id === exercise.id) || initial.planned.some((p) => p.exercise.id === exercise.id)) return s;
      const group: ExerciseGroup = { exerciseId: exercise.id, name: exercise.name, equipment: exercise.equipment, restSeconds: DEFAULT_REST_S, planned: null, rows: [] };
      return {
        ...s,
        extraExercises: [...s.extraExercises, { id: exercise.id, name: exercise.name, equipment: exercise.equipment, restSeconds: DEFAULT_REST_S }],
        rows: [...s.rows, extraRow(group, newId)],
      };
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
        setFinishError(`${flushed.remaining} ${flushed.remaining === 1 ? "set is" : "sets are"} still waiting to be saved. Check the connection and try again.`);
        return;
      }
    }
    const result = await finish(workoutId);
    setFinishing(false);
    if (!result.ok || !result.data) {
      setFinishError(result.ok ? "No answer from the API" : result.error);
      return;
    }
    clearWorkoutState(store, workoutId);
    setSummary(result.data);
  }

  if (summary) {
    return (
      <div className="space-y-4">
        <WorkoutSummaryCard workout={summary} />
        <div className="flex flex-wrap gap-2">
          <Link href={`/training/history/${summary.id}`} className={buttonClass}>
            Open in history
          </Link>
          <Link href="/training" className={secondaryButtonClass}>
            Back to training
          </Link>
        </div>
      </div>
    );
  }

  const startedAt = Date.parse(initial.started_at);
  const logged = local.rows.filter((r) => r.status === "saved").length;

  return (
    <div className="space-y-4 pb-48" data-testid="workout-screen">
      <div className="sticky top-14 z-20 -mx-4 flex items-center justify-between gap-3 border-b border-border bg-bg/95 px-4 py-2 backdrop-blur sm:mx-0 sm:rounded-xl sm:border">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Workout time</p>
          <p className="text-2xl font-semibold tabular-nums" data-testid="workout-elapsed" aria-live="off">
            {formatClock(elapsedMs(startedAt, clock) / 1000)}
          </p>
        </div>
        <div className="text-right text-xs text-muted" aria-live="polite">
          <p>
            {logged} {logged === 1 ? "set" : "sets"} · {formatVolume(loggedVolume(local.rows))}
          </p>
          {queued > 0 ? <p className="text-warn" data-testid="queued-count">{queued} waiting to sync</p> : null}
          {wakeLock === "active" ? <p>Screen stays on</p> : null}
        </div>
      </div>

      {groups.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
          No exercises yet. Add one below.
        </p>
      ) : null}

      {groups.map((group) => (
        <ExerciseCard
          key={group.exerciseId}
          group={group}
          onChange={updateRow}
          onLog={(row) => void logSet(group, row)}
          onAddSet={() => addSet(group)}
          onPlates={(kg) => setPlates({ kg, name: group.name })}
        />
      ))}

      {picking ? (
        <ExercisePicker exercises={exercises} onPick={addExercise} onCancel={() => setPicking(false)} />
      ) : (
        <button type="button" className={`${secondaryButtonClass} min-h-12 w-full`} onClick={() => setPicking(true)}>
          Add exercise
        </button>
      )}

      {finishError ? <ErrorState title="Could not finish the workout" message={finishError} /> : null}
      <button type="button" className={`${buttonClass} min-h-12 w-full text-base`} onClick={() => void onFinish()} disabled={finishing}>
        {finishing ? "Finishing…" : "Finish workout"}
      </button>

      {local.rest ? (
        <RestTimerPanel
          rest={local.rest}
          now={clock}
          onAdjust={(delta) => setRest((rest, t) => adjustRest(rest, delta, t))}
          onSkip={() => setRest(() => null)}
        />
      ) : null}

      {plates ? <PlateSheet targetKg={plates.kg} exerciseName={plates.name} onClose={() => setPlates(null)} /> : null}
    </div>
  );
}

const STATUS_TEXT: Record<SetDraft["status"], string> = {
  idle: "",
  saving: "Saving…",
  saved: "Logged",
  queued: "Saved on this phone, will retry",
  error: "",
};

function ExerciseCard({
  group,
  onChange,
  onLog,
  onAddSet,
  onPlates,
}: {
  group: ExerciseGroup;
  onChange: (clientId: string, change: Partial<SetDraft>) => void;
  onLog: (row: SetDraft) => void;
  onAddSet: () => void;
  onPlates: (kg: number) => void;
}) {
  const planned = group.planned;
  const headingId = `exercise-${group.exerciseId}`;
  // Plates for the next set to do, else the last weight entered.
  const weightOf = (r: SetDraft) => Number(r.weightKg.replace(",", ".")) || 0;
  const next = group.rows.find((r) => r.status !== "saved" && weightOf(r) > 0);
  const lastEntered = [...group.rows].reverse().find((r) => weightOf(r) > 0);
  const plateKg = next ? weightOf(next) : lastEntered ? weightOf(lastEntered) : 0;
  const last = planned?.last_performance?.sets ?? [];
  return (
    <section aria-labelledby={headingId} className="rounded-2xl border border-border bg-surface p-4" data-exercise-id={group.exerciseId}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id={headingId} className="text-base font-semibold tracking-tight">
            {group.name}
          </h2>
          {planned ? (
            <p className="text-xs text-muted">
              {planned.sets} × {planned.rep_min === planned.rep_max ? planned.rep_min : `${planned.rep_min}–${planned.rep_max}`} · rest{" "}
              {group.restSeconds} s
            </p>
          ) : (
            <p className="text-xs text-muted">Rest {group.restSeconds} s</p>
          )}
          {planned?.suggestion.weight_kg != null ? (
            <p className="mt-1 text-xs" data-testid="suggestion">
              Suggested <span className="font-semibold">{formatKg(planned.suggestion.weight_kg)}</span>
              {SUGGESTION_NOTE[planned.suggestion.action]}
            </p>
          ) : null}
        </div>
        {group.equipment === "barbell" && plateKg > 0 ? (
          <button type="button" className={`${secondaryButtonClass} min-h-11 shrink-0`} onClick={() => onPlates(plateKg)}>
            Plates
          </button>
        ) : null}
      </div>
      <ol className="space-y-2">
        {group.rows.map((row) => {
          const lastSet = last[row.setIndex - 1];
          const saved = row.status === "saved";
          const label = `${group.name} set ${row.setIndex}`;
          return (
            <li
              key={row.clientId}
              data-testid="set-row"
              data-status={row.status}
              data-client-id={row.clientId}
              className={`rounded-xl border px-3 py-2 ${saved ? "border-ok/40 bg-ok-soft" : "border-border"}`}
            >
              <div className="flex items-center gap-2">
                <span className="w-10 shrink-0 text-sm font-semibold tabular-nums">#{row.setIndex}</span>
                <label className="min-w-0 flex-1">
                  <span className="sr-only">Reps, {label}</span>
                  <input
                    inputMode="numeric"
                    value={row.reps}
                    onChange={(e) => onChange(row.clientId, { reps: e.target.value })}
                    className="h-12 w-full rounded-lg border border-border bg-surface px-2 text-center text-lg tabular-nums outline-none focus:border-accent"
                  />
                </label>
                <span aria-hidden="true" className="text-muted">×</span>
                <label className="min-w-0 flex-1">
                  <span className="sr-only">Weight in kg, {label}</span>
                  <input
                    inputMode="decimal"
                    value={row.weightKg}
                    onChange={(e) => onChange(row.clientId, { weightKg: e.target.value })}
                    className="h-12 w-full rounded-lg border border-border bg-surface px-2 text-center text-lg tabular-nums outline-none focus:border-accent"
                  />
                </label>
                <span aria-hidden="true" className="text-xs text-muted">kg</span>
                <button
                  type="button"
                  onClick={() => onLog(row)}
                  aria-label={saved ? `Update ${label}` : `Log ${label}`}
                  aria-pressed={saved}
                  disabled={row.status === "saving"}
                  className={`h-12 w-14 shrink-0 rounded-xl text-xl font-bold transition ${
                    saved ? "bg-ok text-white" : "bg-accent text-accent-contrast"
                  } disabled:opacity-60`}
                >
                  ✓
                </button>
              </div>
              <div className="mt-1 flex flex-wrap justify-between gap-x-3 text-xs text-muted">
                <span>{lastSet ? `Last: ${lastSet.reps} × ${formatKg(lastSet.weight_kg)}` : planned ? "Last: none" : ""}</span>
                <span role="status">{row.status === "error" ? <span className="text-bad">{row.error}</span> : STATUS_TEXT[row.status]}</span>
              </div>
            </li>
          );
        })}
      </ol>
      <button type="button" onClick={onAddSet} className="mt-2 min-h-11 rounded-lg px-3 text-sm font-medium text-accent hover:bg-surface-2">
        Add set
      </button>
    </section>
  );
}

const SUGGESTION_NOTE: Record<string, string> = {
  start: " (start weight)",
  increase: " (all reps reached last time)",
  hold: " (same as last time)",
  deload: " (lighter after two short sessions)",
};
