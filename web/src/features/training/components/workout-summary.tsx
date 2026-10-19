import { ArrowLeft, History, Trophy } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Stat } from "@/components/ui/stat";
import { formatClock } from "@/lib/format";
import type { WorkoutDetail } from "@/features/training/types";
import { useTrainingFormat } from "@/features/training/use-training-format";

const MS_PER_S = 1000;

export function workoutDurationS(workout: Pick<WorkoutDetail, "started_at" | "ended_at">): number | null {
  if (!workout.ended_at) return null;
  return Math.max(0, (Date.parse(workout.ended_at) - Date.parse(workout.started_at)) / MS_PER_S);
}

/** Duration, total volume, sets and the records this workout set. */
export function WorkoutSummaryCard({ workout }: { workout: WorkoutDetail }) {
  const t = useTranslations("workout.summary");
  const fmt = useTrainingFormat();
  const duration = workoutDurationS(workout);
  return (
    <div className="flex flex-col gap-4" data-testid="workout-summary" data-volume={workout.volume_kg}>
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.08em] text-accent-ink">{fmt.dateTime(workout.started_at)}</p>
        <h2 className="text-2xl font-black tracking-tight">{workout.program_day_name ?? t("freeWorkout")}</h2>
      </div>
      <Card>
        <dl className="grid grid-cols-3 gap-3">
          <Stat label={t("duration")} value={duration === null ? t("inProgress") : formatClock(duration)} />
          <Stat label={t("volume")} value={fmt.volume(workout.volume_kg)} />
          <Stat label={t("sets")} value={fmt.number(workout.set_count)} />
        </dl>
      </Card>
      <Card aria-labelledby={`records-${workout.id}`}>
        <CardHeader>
          <CardTitle id={`records-${workout.id}`}>{t("records", { count: workout.records.length })}</CardTitle>
          <Trophy aria-hidden className="size-5 text-accent-ink" />
        </CardHeader>
        {workout.records.length === 0 ? (
          <p className="text-sm text-muted">{t("noRecords")}</p>
        ) : (
          <ul className="divide-y divide-border text-sm" data-testid="workout-records">
            {workout.records.map((r, i) => (
              <li key={i} className="flex flex-wrap items-baseline justify-between gap-2 py-2">
                <span className="font-medium">{r.exercise_name}</span>
                <span className="text-muted">
                  {fmt.kind(r.kind)}: <span className="font-semibold text-text">{fmt.record(r)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

/** The end of the workout screen: the summary and the way on. */
export function WorkoutFinished({ workout }: { workout: WorkoutDetail }) {
  const t = useTranslations("workout.summary");
  return (
    <div className="flex flex-col gap-4">
      <p role="status" className="text-3xl font-black tracking-tight text-accent-ink">
        {t("done")}
      </p>
      <WorkoutSummaryCard workout={workout} />
      <div className="flex flex-col gap-2 sm:flex-row">
        <Button asChild size="lg">
          <Link href={`/training/history/${workout.id}`}>
            <History aria-hidden />
            {t("openHistory")}
          </Link>
        </Button>
        <Button asChild size="lg" variant="secondary">
          <Link href="/training">
            <ArrowLeft aria-hidden />
            {t("back")}
          </Link>
        </Button>
      </div>
    </div>
  );
}
