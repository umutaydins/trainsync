import type { Metadata } from "next";

import { PrBoard } from "@/features/training/components/pr-board";
import { BodyWeightChart, ExerciseProgressChart, WeeklyMuscleChart } from "@/features/training/components/progress-charts";
import { Card, EmptyState, ErrorState, PageHeader, buttonClass, inputClass } from "@/components/ui";
import { load } from "@/lib/api";
import { trainingApi } from "@/features/training/api";

export const metadata: Metadata = { title: "Progress" };
export const dynamic = "force-dynamic";

/** `/training/progress?exercise=<id>`: e1RM/best set per exercise, weekly muscle volume, records, body weight. */
export default async function ProgressPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = (await searchParams).exercise;
  const [exercises, records, weekly, weights] = await Promise.all([
    load(() => trainingApi.exercises()),
    load(() => trainingApi.records()),
    load(() => trainingApi.weeklyVolume()),
    load(() => trainingApi.bodyMetrics()),
  ]);
  // Exercises with records first: those are the ones with history.
  const trained = records.ok ? [...new Set(records.data.items.map((r) => r.exercise_id))] : [];
  const requested = typeof raw === "string" && /^\d{1,20}$/.test(raw) ? Number(raw) : null;
  const exerciseId = requested ?? trained[0] ?? null;
  const progress = exerciseId === null ? null : await load(() => trainingApi.exerciseProgress(exerciseId));
  const list = exercises.ok ? exercises.data.items : [];
  const options = [...list.filter((e) => trained.includes(e.id)), ...list.filter((e) => !trained.includes(e.id))];

  return (
    <>
      <PageHeader title="Progress" subtitle="Strength, volume and records" />
      <div className="space-y-4">
        <Card title="Exercise" labelledBy="exercise-title">
          <form method="get" className="mb-4 flex items-end gap-2">
            <label className="block flex-1 text-sm font-medium">
              Exercise
              <select name="exercise" defaultValue={exerciseId ?? undefined} className={`${inputClass} mt-1 min-h-11`}>
                {options.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" className={`${buttonClass} min-h-11`}>
              Show
            </button>
          </form>
          {progress === null ? (
            <EmptyState title="No exercise yet">Log a workout to see progress here.</EmptyState>
          ) : !progress.ok ? (
            <ErrorState title="Could not load progress" message={progress.error} />
          ) : progress.data.sessions.length === 0 ? (
            <EmptyState title={`No sets of ${progress.data.exercise.name} yet`} />
          ) : (
            <ExerciseProgressChart progress={progress.data} />
          )}
        </Card>

        <Card title="Weekly volume per muscle" labelledBy="muscle-title">
          {!weekly.ok ? (
            <ErrorState title="Could not load weekly volume" message={weekly.error} />
          ) : weekly.data.items.length === 0 ? (
            <EmptyState title="No working sets in the last 12 weeks" />
          ) : (
            <WeeklyMuscleChart items={weekly.data.items} />
          )}
        </Card>

        <Card title="Records" labelledBy="records-title">
          {records.ok ? <PrBoard records={records.data.items} /> : <ErrorState title="Could not load records" message={records.error} />}
        </Card>

        {weights.ok && weights.data.items.length > 0 ? (
          <Card title="Body weight" labelledBy="weight-title">
            <BodyWeightChart items={weights.data.items} />
          </Card>
        ) : null}
      </div>
    </>
  );
}
