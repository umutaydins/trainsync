import { Dumbbell, Play } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Empty, Failure } from "@/components/ui/states";
import { nextPlanned, plannedOn, weekdayOfDate } from "@/features/today/schedule";
import { StartWorkoutButton } from "@/features/training/components/start-workout";
import type { ProgramOut, WorkoutPage } from "@/features/training/types";
import type { Loaded } from "@/lib/api";

const NOT_FOUND = 404;
/** The plan lists this many exercises; the workout screen has the rest. */
const SHOWN_EXERCISES = 4;
/** Any Monday, to name a weekday in the user's language. */
const MONDAY = Date.UTC(2024, 0, 1);
const DAY_MS = 86_400_000;

/**
 * Today's workout from the active program (the coach's weekday rule): start it with one big
 * button, continue an open one, or see what is next on a rest day.
 */
export function PlannedWorkout({
  program,
  workouts,
  today,
}: {
  program: Loaded<ProgramOut>;
  workouts: Loaded<WorkoutPage>;
  today: string;
}) {
  const t = useTranslations("today.workout");
  const locale = useLocale();
  const open = workouts.ok ? workouts.data.items.find((w) => w.ended_at === null) : undefined;
  const weekdayName = (weekday: number) =>
    new Intl.DateTimeFormat(locale, { weekday: "long", timeZone: "UTC" }).format(MONDAY + weekday * DAY_MS);

  if (open) {
    return (
      <Card aria-labelledby="workout-title" data-testid="today-workout">
        <Title>{t("title")}</Title>
        <p className="text-2xl font-black tracking-tight">{open.program_day_name ?? t("freeWorkout")}</p>
        <p className="mt-1 text-sm text-muted">{t("inProgress", { sets: open.set_count })}</p>
        <Link href={`/training/workout/${open.id}`} className={buttonVariants({ size: "lg", block: true, className: "mt-4" })}>
          <Play aria-hidden />
          {t("resume")}
        </Link>
      </Card>
    );
  }
  if (!program.ok) {
    if (program.status !== NOT_FOUND) return <Failure title={t("failed")} message={program.error} />;
    return (
      <Empty
        title={t("noProgram")}
        action={
          <Link href="/training" className={buttonVariants({ variant: "primary" })}>
            <Dumbbell aria-hidden />
            {t("pickProgram")}
          </Link>
        }
      >
        {t("noProgramHint")}
      </Empty>
    );
  }

  const weekday = weekdayOfDate(today);
  const day = plannedOn(program.data, weekday);
  if (!day) {
    const next = nextPlanned(program.data, weekday);
    return (
      <Card aria-labelledby="workout-title" data-testid="today-workout">
        <Title>{t("title")}</Title>
        <p className="text-2xl font-black tracking-tight">{t("rest")}</p>
        {next ? <p className="mt-1 text-sm text-muted">{t("next", { day: next.day.name, weekday: weekdayName(next.weekday) })}</p> : null}
        <Link href="/training" className={buttonVariants({ variant: "secondary", block: true, className: "mt-4" })}>
          {t("seeProgram")}
        </Link>
      </Card>
    );
  }

  const names = day.exercises.map((e) => e.exercise.name);
  const rest = names.length - SHOWN_EXERCISES;
  return (
    <Card aria-labelledby="workout-title" data-testid="today-workout" className="border-accent/40">
      <Title>{t("title")}</Title>
      <p className="text-3xl font-black tracking-tight">{day.name}</p>
      <p className="mt-1 text-sm text-muted">{program.data.name}</p>
      <ul className="mt-3 flex flex-wrap gap-1.5 text-sm">
        {names.slice(0, SHOWN_EXERCISES).map((name, index) => (
          <li key={`${name}-${index}`} className="rounded-full bg-surface-2 px-3 py-1">
            {name}
          </li>
        ))}
        {rest > 0 ? <li className="rounded-full px-2 py-1 text-muted">{t("more", { count: rest })}</li> : null}
      </ul>
      <div className="mt-4 [&_button]:h-14 [&_button]:w-full [&_button]:text-base">
        <StartWorkoutButton programDayId={day.id} label={t("start")} busyLabel={t("starting")} />
      </div>
    </Card>
  );
}

function Title({ children }: { children: string }) {
  return (
    <h2 id="workout-title" className="mb-2 text-label font-semibold uppercase tracking-[0.08em] text-muted">
      {children}
    </h2>
  );
}
