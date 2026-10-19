import { Dumbbell, Play } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { PageTitle } from "@/components/ui/page-header";
import { Empty } from "@/components/ui/states";
import { LoadFailed } from "@/features/shell/components/load-failed";
import { StartWorkoutButton } from "@/features/training/components/start-workout";
import type { ProgramOut, WorkoutPage } from "@/features/training/types";
import { useTrainingFormat } from "@/features/training/use-training-format";
import type { Loaded } from "@/lib/api";

const NOT_FOUND = 404;

/** `/training`, the gym entry point (PWA start_url): open workouts, the active program's days, a free start. */
export function TrainingHome({ program, workouts }: { program: Loaded<ProgramOut>; workouts: Loaded<WorkoutPage> }) {
  const t = useTranslations("training");
  const open = workouts.ok ? workouts.data.items.filter((w) => w.ended_at === null) : [];
  return (
    <div className="flex flex-col gap-4">
      <PageTitle title={t("title")} subtitle={t("subtitle")} />
      {workouts.ok ? null : <LoadFailed title={t("home.workoutsFailed")} status={workouts.status} />}
      {open.length > 0 ? <OpenWorkouts open={open} /> : null}
      <ActiveProgram program={program} />
      <Card className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted">{t("home.freeHint")}</p>
        <StartWorkoutButton label={t("home.free")} secondary />
      </Card>
    </div>
  );
}

function OpenWorkouts({ open }: { open: WorkoutPage["items"] }) {
  const t = useTranslations("training.home");
  const fmt = useTrainingFormat();
  return (
    <Card aria-labelledby="open-title" className="border-accent/40">
      <CardHeader>
        <CardTitle id="open-title">{t("inProgress")}</CardTitle>
      </CardHeader>
      <ul className="divide-y divide-border">
        {open.map((w) => (
          <li key={w.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <p className="text-lg font-bold">{w.program_day_name ?? t("freeWorkout")}</p>
              <p className="text-sm text-muted">{t("started", { time: fmt.dateTime(w.started_at), sets: w.set_count, volume: fmt.volume(w.volume_kg) })}</p>
            </div>
            <Button asChild size="lg">
              <Link href={`/training/workout/${w.id}`}>
                <Play aria-hidden />
                {t("resume")}
              </Link>
            </Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function ActiveProgram({ program }: { program: Loaded<ProgramOut> }) {
  const t = useTranslations("training.home");
  const goals = useTranslations("training.goals");
  if (!program.ok) {
    if (program.status !== NOT_FOUND) return <LoadFailed title={t("programFailed")} status={program.status} />;
    return (
      <Empty
        title={t("noProgram")}
        action={
          <Button asChild>
            <Link href="/training/programs">
              <Dumbbell aria-hidden />
              {t("toPrograms")}
            </Link>
          </Button>
        }
      >
        {t("noProgramHint")}
      </Empty>
    );
  }
  const p = program.data;
  return (
    <Card aria-labelledby="active-title">
      <CardHeader className="flex-wrap">
        <h2 id="active-title" className="text-2xl font-black tracking-tight">
          {p.name}
        </h2>
        <Badge tone="accent">{t("programMeta", { goal: goals(p.goal), days: p.days_per_week })}</Badge>
      </CardHeader>
      <ul className="flex flex-col gap-3" data-testid="program-days">
        {p.days.map((day) => (
          <li key={day.id} className="flex flex-col gap-3 rounded-card border border-border bg-surface-2/40 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-label font-semibold uppercase tracking-[0.08em] text-muted">{t("day", { index: day.day_index + 1 })}</p>
              <p className="text-lg font-bold">{day.name}</p>
              <p className="text-sm text-muted">{day.exercises.map((e) => e.exercise.name).join(" · ")}</p>
            </div>
            <StartWorkoutButton programDayId={day.id} label={t("startDay", { name: day.name })} />
          </li>
        ))}
      </ul>
    </Card>
  );
}
