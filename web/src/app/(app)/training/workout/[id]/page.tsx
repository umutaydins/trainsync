import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { PageTitle } from "@/components/ui/page-header";
import { LoadFailed } from "@/features/shell/components/load-failed";
import { trainingApi } from "@/features/training/api";
import { WorkoutLoader } from "@/features/training/components/workout-loader";
import { WorkoutSummaryCard } from "@/features/training/components/workout-summary";
import { load } from "@/lib/api";

export const dynamic = "force-dynamic";

const NOT_FOUND = 404;
type Props = { params: Promise<{ id: string }> };

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("workout");
  return { title: t("title") };
}

/** `/training/workout/[id]`: the active workout, or the summary of a finished one. */
export default async function WorkoutPage({ params }: Props) {
  const raw = (await params).id;
  if (!/^\d{1,20}$/.test(raw)) notFound();
  const t = await getTranslations("workout");
  const [workout, exercises] = await Promise.all([load(() => trainingApi.workout(Number(raw))), load(() => trainingApi.exercises())]);
  if (!workout.ok && workout.status === NOT_FOUND) notFound();
  if (!workout.ok) return <LoadFailed title={t("loadFailed")} status={workout.status} />;
  return (
    <div className="mx-auto w-full max-w-2xl">
      <PageTitle title={workout.data.program_day_name ?? t("summary.freeWorkout")} />
      {workout.data.ended_at ? (
        <WorkoutSummaryCard workout={workout.data} />
      ) : (
        <WorkoutLoader initial={workout.data} exercises={exercises.ok ? exercises.data.items : []} />
      )}
    </div>
  );
}
