"use client";

import Link from "next/link";
import { useState } from "react";

import { EmptyState, ErrorState, secondaryButtonClass } from "@/components/ui";
import { workoutDurationS } from "@/components/training/workout-summary";
import { bffGet } from "@/lib/bff-get";
import { formatClock, formatDateTime } from "@/lib/format";
import type { WorkoutPage, WorkoutSummary } from "@/lib/training-types";
import { HISTORY_PAGE_SIZE, formatVolume } from "@/lib/training-types";

/** Workouts, newest first; "Load more" follows `next_cursor` (keyset, ADR 0009). */
export function HistoryList({ initial }: { initial: WorkoutPage }) {
  const [items, setItems] = useState<WorkoutSummary[]>(initial.items);
  const [cursor, setCursor] = useState(initial.next_cursor);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function more() {
    if (!cursor || loading) return;
    setLoading(true);
    setError(null);
    const result = await bffGet<WorkoutPage>("/v1/training/workouts", { limit: HISTORY_PAGE_SIZE, cursor });
    setLoading(false);
    if (!result.ok || !result.data) return setError(result.ok ? "Empty answer" : result.error);
    const page = result.data;
    setItems((current) => {
      const seen = new Set(current.map((w) => w.id));
      return [...current, ...page.items.filter((w) => !seen.has(w.id))];
    });
    setCursor(page.next_cursor);
  }

  if (items.length === 0) {
    return (
      <EmptyState title="No workouts yet">
        <Link href="/training" className="text-accent hover:underline">
          Start one
        </Link>
      </EmptyState>
    );
  }

  return (
    <div className="space-y-3">
      <ul className="divide-y divide-border rounded-2xl border border-border bg-surface" data-testid="workout-history">
        {items.map((w) => {
          const duration = workoutDurationS(w);
          return (
            <li key={w.id} data-workout-id={w.id} data-volume={w.volume_kg}>
              <Link
                href={w.ended_at ? `/training/history/${w.id}` : `/training/workout/${w.id}`}
                className="flex min-h-14 flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3 hover:bg-surface-2"
              >
                <span>
                  <span className="block font-medium">{w.program_day_name ?? "Workout"}</span>
                  <span className="block text-xs text-muted">{formatDateTime(w.started_at)}</span>
                </span>
                <span className="text-right text-sm tabular-nums">
                  <span className="block font-semibold">{formatVolume(w.volume_kg)}</span>
                  <span className="block text-xs text-muted">
                    {w.set_count} sets · {duration === null ? "in progress" : formatClock(duration)}
                  </span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      {error ? <ErrorState title="Could not load more workouts" message={error} /> : null}
      <div className="flex justify-end">
        {cursor ? (
          <button type="button" className={`${secondaryButtonClass} min-h-11`} onClick={() => void more()} disabled={loading}>
            {loading ? "Loading…" : "Load more"}
          </button>
        ) : (
          <p className="text-sm text-muted">End of list</p>
        )}
      </div>
    </div>
  );
}
