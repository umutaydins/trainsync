/**
 * Workout and rest timers, timestamp-based: state holds absolute times (epoch ms) and the UI
 * renders `endsAt - now()`. A tab that was backgrounded or a phone whose screen locked (where
 * intervals are throttled or frozen) shows the right value on the next render. Pure functions with
 * an injected `now`, so tests drive time without real sleeps.
 */

export type Now = () => number;
export const systemNow: Now = () => Date.now();

export interface RestTimer {
  /** When the rest ends (epoch ms). */
  endsAt: number;
  /** The planned length, for the progress ring (seconds, after ± adjustments). */
  durationS: number;
  /** What the rest follows, e.g. "Bench Press · set 2". */
  label: string;
  /** Set once the zero alert (vibration, sound, notification) has fired, so a reload does not repeat it. */
  alerted: boolean;
}

export const REST_STEP_S = 15;
/** An alert this late (the tab was asleep through zero) is skipped; the timer just shows 0:00. */
export const LATE_ALERT_MS = 60_000;

export function startRest(now: number, seconds: number, label: string): RestTimer {
  const durationS = Math.max(0, Math.round(seconds));
  return { endsAt: now + durationS * 1000, durationS, label, alerted: false };
}

/** Milliseconds left, never negative. */
export function remainingMs(timer: RestTimer, now: number): number {
  return Math.max(0, timer.endsAt - now);
}

/** Whole seconds left, rounded up so the display reaches 0 exactly at `endsAt`. */
export function remainingSeconds(timer: RestTimer, now: number): number {
  return Math.ceil(remainingMs(timer, now) / 1000);
}

export function isFinished(timer: RestTimer, now: number): boolean {
  return now >= timer.endsAt;
}

/** +15 s / −15 s. Never ends before `now`; extending a finished timer restarts it from now. */
export function adjustRest(timer: RestTimer, deltaS: number, now: number): RestTimer {
  const base = Math.max(timer.endsAt, now);
  const endsAt = Math.max(now, base + deltaS * 1000);
  const durationS = Math.max(0, timer.durationS + deltaS);
  return { ...timer, endsAt, durationS, alerted: endsAt > now ? false : timer.alerted };
}

/** Whether the zero alert should fire now: finished, not alerted yet, and not stale. */
export function shouldAlert(timer: RestTimer, now: number): boolean {
  return !timer.alerted && isFinished(timer, now) && now - timer.endsAt <= LATE_ALERT_MS;
}

/** 0..1 of the rest that has passed. */
export function restProgress(timer: RestTimer, now: number): number {
  if (timer.durationS <= 0) return 1;
  return Math.min(1, Math.max(0, 1 - remainingMs(timer, now) / (timer.durationS * 1000)));
}

export function elapsedMs(startedAt: number, now: number): number {
  return Math.max(0, now - startedAt);
}

// ---------------------------------------------------------------- persistence

/** One planned or extra set row as the screen keeps it until the API confirms it. */
export interface SetDraft {
  /** Generated once per row (crypto.randomUUID), reused for every attempt (ADR 0017). */
  clientId: string;
  exerciseId: number;
  setIndex: number;
  reps: string;
  weightKg: string;
  /** Fixed at the first tap, so retries do not move the set in time. */
  completedAt: string | null;
  status: "idle" | "saving" | "saved" | "queued" | "error";
  error?: string;
}

export interface WorkoutLocalState {
  version: 1;
  workoutId: number;
  rest: RestTimer | null;
  rows: SetDraft[];
  /** Exercises added during the workout that are not in the plan (id → name, equipment). */
  extraExercises: { id: number; name: string; equipment: string; restSeconds: number }[];
}

export function storageKey(workoutId: number): string {
  return `trainsync.workout.${workoutId}`;
}

/** Storage that may be missing (private mode, SSR) or throw (quota): every call is guarded. */
export type KeyValueStore = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function browserStorage(): KeyValueStore | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function loadWorkoutState(store: KeyValueStore | null, workoutId: number): WorkoutLocalState | null {
  if (!store) return null;
  try {
    const raw = store.getItem(storageKey(workoutId));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<WorkoutLocalState>;
    if (value.version !== 1 || value.workoutId !== workoutId || !Array.isArray(value.rows)) return null;
    return {
      version: 1,
      workoutId,
      rest: isRestTimer(value.rest) ? value.rest : null,
      rows: value.rows.filter(isSetDraft),
      extraExercises: Array.isArray(value.extraExercises) ? value.extraExercises : [],
    };
  } catch {
    return null;
  }
}

export function saveWorkoutState(store: KeyValueStore | null, state: WorkoutLocalState): void {
  if (!store) return;
  try {
    store.setItem(storageKey(state.workoutId), JSON.stringify(state));
  } catch {
    // Quota or disabled storage: the screen still works, it just will not survive a reload.
  }
}

export function clearWorkoutState(store: KeyValueStore | null, workoutId: number): void {
  try {
    store?.removeItem(storageKey(workoutId));
  } catch {
    // ignore
  }
}

function isRestTimer(value: unknown): value is RestTimer {
  const v = value as RestTimer | null;
  return !!v && typeof v.endsAt === "number" && typeof v.durationS === "number" && typeof v.label === "string";
}

function isSetDraft(value: unknown): value is SetDraft {
  const v = value as SetDraft | null;
  return !!v && typeof v.clientId === "string" && typeof v.exerciseId === "number" && typeof v.setIndex === "number";
}
