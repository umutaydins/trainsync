import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { WorkoutSets } from "@/features/training/components/workout-sets";
import { WorkoutSummaryCard } from "@/features/training/components/workout-summary";
import { ErrorState } from "@/components/ui";
import { load } from "@/lib/api";
import { trainingApi } from "@/features/training/api";

export const metadata: Metadata = { title: "Workout" };
export const dynamic = "force-dynamic";

export default async function HistoryDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const raw = (await params).id;
  if (!/^\d{1,20}$/.test(raw)) notFound();
  const [workout, exercises] = await Promise.all([load(() => trainingApi.workout(Number(raw))), load(() => trainingApi.exercises())]);
  if (!workout.ok && workout.status === 404) notFound();
  return (
    <>
      <Link href="/training/history" className="mb-4 inline-flex min-h-11 items-center text-sm text-muted hover:text-text">
        ← History
      </Link>
      {workout.ok ? (
        <div className="space-y-4">
          <h1 className="sr-only">Workout</h1>
          <WorkoutSummaryCard workout={workout.data} />
          <WorkoutSets workout={workout.data} exercises={new Map((exercises.ok ? exercises.data.items : []).map((e) => [e.id, e]))} />
        </div>
      ) : (
        <ErrorState title="Could not load this workout" message={workout.error} />
      )}
    </>
  );
}
