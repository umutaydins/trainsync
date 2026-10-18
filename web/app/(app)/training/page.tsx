import type { Metadata } from "next";
import Link from "next/link";

import { StartWorkoutButton } from "@/components/training/start-workout";
import { Badge, Card, EmptyState, ErrorState, PageHeader, buttonClass } from "@/components/ui";
import { load } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { trainingApi } from "@/lib/training-api";
import { formatVolume, label } from "@/lib/training-types";

export const metadata: Metadata = { title: "Training" };
export const dynamic = "force-dynamic";

/** The gym entry point (PWA start_url): today's options from the active program, open workouts. */
export default async function TrainingPage() {
  const [active, workouts] = await Promise.all([
    load(() => trainingApi.activeProgram()),
    load(() => trainingApi.workouts(10)),
  ]);
  const open = workouts.ok ? workouts.data.items.filter((w) => w.ended_at === null) : [];

  return (
    <>
      <PageHeader title="Training" subtitle="Pick a day and start" />
      <div className="space-y-4">
        {open.length > 0 ? (
          <Card title="In progress" labelledBy="open-title">
            <ul className="divide-y divide-border">
              {open.map((w) => (
                <li key={w.id} className="flex items-center justify-between gap-3 py-2">
                  <div>
                    <p className="font-medium">{w.program_day_name ?? "Workout"}</p>
                    <p className="text-xs text-muted">
                      Started {formatDateTime(w.started_at)} · {w.set_count} sets · {formatVolume(w.volume_kg)}
                    </p>
                  </div>
                  <Link href={`/training/workout/${w.id}`} className={`${buttonClass} min-h-11`}>
                    Resume
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        ) : null}

        {active.ok ? (
          <Card
            title={active.data.name}
            labelledBy="active-title"
            action={<Badge tone="accent">{label(active.data.goal)} · {active.data.days_per_week} days</Badge>}
          >
            <ul className="space-y-3" data-testid="program-days">
              {active.data.days.map((day) => (
                <li key={day.id} className="flex flex-col gap-2 rounded-xl border border-border p-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="font-medium">
                      Day {day.day_index + 1}: {day.name}
                    </p>
                    <p className="text-xs text-muted">{day.exercises.map((e) => e.exercise.name).join(" · ")}</p>
                  </div>
                  <StartWorkoutButton programDayId={day.id} label={`Start ${day.name}`} />
                </li>
              ))}
            </ul>
          </Card>
        ) : active.status === 404 ? (
          <Card title="No active program" labelledBy="none-title">
            <EmptyState title="No program is active">
              <Link href="/training/programs" className="text-accent hover:underline">
                Generate or activate a program
              </Link>
            </EmptyState>
          </Card>
        ) : (
          <ErrorState title="Could not load the active program" message={active.error} />
        )}

        <div className="flex flex-wrap gap-2">
          <StartWorkoutButton label="Start an empty workout" secondary />
        </div>
      </div>
    </>
  );
}
