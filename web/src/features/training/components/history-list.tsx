"use client";

import { ChevronRight, Dumbbell } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Empty } from "@/components/ui/states";
import { LoadFailed } from "@/features/shell/components/load-failed";
import { workoutDurationS } from "@/features/training/components/workout-summary";
import type { WorkoutPage, WorkoutSummary } from "@/features/training/types";
import { HISTORY_PAGE_SIZE } from "@/features/training/types";
import { useTrainingFormat } from "@/features/training/use-training-format";
import { bffGet } from "@/lib/bff-get";
import { formatClock } from "@/lib/format";

/** Workouts, newest first; "Load more" follows `next_cursor` (keyset, ADR 0009). */
export function HistoryList({ initial }: { initial: WorkoutPage }) {
  const t = useTranslations("training.history");
  const home = useTranslations("training.home");
  const common = useTranslations("common.actions");
  const states = useTranslations("common.states");
  const fmt = useTrainingFormat();
  const [items, setItems] = useState<WorkoutSummary[]>(initial.items);
  const [cursor, setCursor] = useState(initial.next_cursor);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState<number | null>(null);

  async function more() {
    if (!cursor || loading) return;
    setLoading(true);
    setFailed(null);
    const result = await bffGet<WorkoutPage>("/v1/training/workouts", { limit: HISTORY_PAGE_SIZE, cursor });
    setLoading(false);
    if (!result.ok || !result.data) return setFailed(result.status);
    const page = result.data;
    setItems((current) => {
      const seen = new Set(current.map((w) => w.id));
      return [...current, ...page.items.filter((w) => !seen.has(w.id))];
    });
    setCursor(page.next_cursor);
  }

  if (items.length === 0) {
    return (
      <Empty
        title={t("empty")}
        action={
          <Button asChild>
            <Link href="/training">
              <Dumbbell aria-hidden />
              {t("start")}
            </Link>
          </Button>
        }
      >
        {t("emptyHint")}
      </Empty>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <ul className="divide-y divide-border overflow-hidden rounded-card border border-border bg-surface shadow-card" data-testid="workout-history">
        {items.map((w) => {
          const duration = workoutDurationS(w);
          return (
            <li key={w.id} data-workout-id={w.id} data-volume={w.volume_kg}>
              <Link
                href={w.ended_at ? `/training/history/${w.id}` : `/training/workout/${w.id}`}
                className="flex min-h-16 items-center justify-between gap-3 px-4 py-3 transition hover:bg-surface-2"
              >
                <span className="min-w-0">
                  <span className="block truncate font-semibold">{w.program_day_name ?? home("freeWorkout")}</span>
                  <span className="block text-xs text-muted">{fmt.dateTime(w.started_at)}</span>
                </span>
                <span className="flex items-center gap-2 text-right tabular">
                  <span>
                    <span className="block text-lg font-bold">{fmt.volume(w.volume_kg)}</span>
                    <span className="block text-xs text-muted">
                      {t("meta", { sets: w.set_count, duration: duration === null ? t("inProgress") : formatClock(duration) })}
                    </span>
                  </span>
                  <ChevronRight aria-hidden className="size-4 text-muted" />
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      {failed !== null ? <LoadFailed title={t("moreFailed")} status={failed} /> : null}
      <div className="flex justify-center">
        {cursor ? (
          <Button variant="secondary" onClick={() => void more()} disabled={loading}>
            {loading ? states("loading") : failed !== null ? common("retry") : common("loadMore")}
          </Button>
        ) : (
          <p className="text-sm text-muted">{common("endOfList")}</p>
        )}
      </div>
    </div>
  );
}
