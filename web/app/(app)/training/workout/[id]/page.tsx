import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { WorkoutLoader } from "@/components/training/workout-loader";
import { WorkoutSummaryCard } from "@/components/training/workout-summary";
import { ErrorState } from "@/components/ui";
import { load } from "@/lib/api";
import { trainingApi } from "@/lib/training-api";

export const metadata: Metadata = { title: "Workout" };
export const dynamic = "force-dynamic";

type Props = { params: Promise<{ id: string }> };

export default async function WorkoutPage({ params }: Props) {
  const raw = (await params).id;
  if (!/^\d{1,20}$/.test(raw)) notFound();
  const id = Number(raw);
  const [workout, exercises] = await Promise.all([
    load(() => trainingApi.workout(id)),
    load(() => trainingApi.exercises()),
  ]);
  if (!workout.ok && workout.status === 404) notFound();
  if (!workout.ok) return <ErrorState title="Could not load this workout" message={workout.error} />;
  return (
    <>
      <h1 className="mb-3 text-2xl font-semibold tracking-tight">{workout.data.program_day_name ?? "Workout"}</h1>
      {workout.data.ended_at ? (
        <WorkoutSummaryCard workout={workout.data} />
      ) : (
        <WorkoutLoader initial={workout.data} exercises={exercises.ok ? exercises.data.items : []} />
      )}
    </>
  );
}
