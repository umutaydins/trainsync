"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { type Now, type RestTimer, shouldAlert } from "@/features/training/timers";

export const TICK_MS = 250;

/**
 * The screen's clock: re-renders every `TICK_MS` and as soon as a backgrounded tab is back
 * (intervals are throttled or frozen there). When the rest reaches zero it calls `onRestOver`
 * once; a rest the phone slept through (more than a minute late) is only marked, not signalled.
 */
export function useWorkoutClock({
  rest,
  now,
  onRestOver,
  markAlerted,
}: {
  rest: RestTimer | null;
  now: Now;
  onRestOver: (rest: RestTimer) => void;
  markAlerted: () => void;
}): { clock: number; sync: () => void } {
  const [clock, setClock] = useState(() => now());
  const restRef = useRef(rest);
  // `endsAt` of the rest already signalled; the state update lands a render later than the next tick.
  const alertedAt = useRef<number | null>(null);
  const handlers = useRef({ onRestOver, markAlerted });
  useEffect(() => {
    restRef.current = rest;
    handlers.current = { onRestOver, markAlerted };
  });

  const tick = useCallback(() => {
    const t = now();
    setClock(t);
    const current = restRef.current;
    if (!current || current.alerted || alertedAt.current === current.endsAt) return;
    if (shouldAlert(current, t)) {
      alertedAt.current = current.endsAt;
      handlers.current.onRestOver(current);
      handlers.current.markAlerted();
    } else if (t > current.endsAt) {
      alertedAt.current = current.endsAt;
      handlers.current.markAlerted();
    }
  }, [now]);

  useEffect(() => {
    const timer = setInterval(tick, TICK_MS);
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

  return { clock, sync: () => setClock(now()) };
}
