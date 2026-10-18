"use client";

import { useState } from "react";

import { notificationPermission, requestNotifications } from "@/lib/alerts";
import { formatClock } from "@/lib/format";
import { type RestTimer, REST_STEP_S, isFinished, remainingSeconds, restProgress } from "@/lib/timers";

/** The rest countdown, pinned to the bottom of the screen. Renders from `endsAt` and `now`. */
export function RestTimerPanel({
  rest,
  now,
  onAdjust,
  onSkip,
}: {
  rest: RestTimer;
  now: number;
  onAdjust: (deltaS: number) => void;
  onSkip: () => void;
}) {
  const [permission, setPermission] = useState(() => notificationPermission());
  const done = isFinished(rest, now);
  const left = remainingSeconds(rest, now);
  const progress = restProgress(rest, now);
  const big = "min-h-12 flex-1 rounded-xl border border-border bg-surface text-base font-semibold active:bg-surface-2";

  return (
    <div
      role="region"
      aria-label="Rest timer"
      data-testid="rest-timer"
      data-remaining={left}
      className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-surface/95 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 shadow-[0_-4px_16px_rgba(0,0,0,0.08)] backdrop-blur"
    >
      <div className="mx-auto max-w-lg">
        <div className="flex items-baseline justify-between gap-3">
          <p className="truncate text-xs text-muted">{done ? "Rest over" : `Rest after ${rest.label}`}</p>
          <p className={`text-4xl font-semibold tabular-nums ${done ? "text-ok" : ""}`} aria-live="off" data-testid="rest-remaining">
            {formatClock(left)}
          </p>
        </div>
        <div
          role="progressbar"
          aria-label="Rest"
          aria-valuemin={0}
          aria-valuemax={rest.durationS}
          aria-valuenow={rest.durationS - left}
          className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2"
        >
          <div className="h-full bg-accent" style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>
        <p className="sr-only" aria-live="assertive">
          {done ? "Rest over" : ""}
        </p>
        <div className="mt-3 flex gap-2">
          <button type="button" className={big} onClick={() => onAdjust(-REST_STEP_S)} aria-label="Rest 15 seconds shorter">
            −15 s
          </button>
          <button type="button" className={big} onClick={() => onAdjust(REST_STEP_S)} aria-label="Rest 15 seconds longer">
            +15 s
          </button>
          <button type="button" className={`${big} bg-accent text-accent-contrast`} onClick={onSkip}>
            {done ? "Done" : "Skip"}
          </button>
        </div>
        {permission === "default" ? (
          <button
            type="button"
            className="mt-2 min-h-11 w-full rounded-lg text-sm text-muted hover:text-text"
            onClick={async () => setPermission(await requestNotifications())}
          >
            Notify me when the rest is over
          </button>
        ) : null}
      </div>
    </div>
  );
}
