import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { LoadFailed } from "@/features/shell/components/load-failed";
import { trainingApi } from "@/features/training/api";
import { WorkoutSets } from "@/features/training/components/workout-sets";
import { WorkoutSummaryCard } from "@/features/training/components/workout-summary";
import { load } from "@/lib/api";

export const dynamic = "force-dynamic";

const NOT_FOUND = 404;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("workout");
  return { title: t("title") };
}

export default async function HistoryDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const raw = (await params).id;
  if (!/^\d{1,20}$/.test(raw)) notFound();
  const [t, w] = await Promise.all([getTranslations("training.history"), getTranslations("workout")]);
  const [workout, exercises] = await Promise.all([load(() => trainingApi.workout(Number(raw))), load(() => trainingApi.exercises())]);
  if (!workout.ok && workout.status === NOT_FOUND) notFound();
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <Link href="/training/history" className="-ml-2 inline-flex h-touch items-center gap-1.5 self-start rounded-control px-2 text-sm font-semibold text-muted hover:text-text">
        <ArrowLeft aria-hidden className="size-4" />
        {t("back")}
      </Link>
      {workout.ok ? (
        <>
          <h1 className="sr-only">{w("title")}</h1>
          <WorkoutSummaryCard workout={workout.data} />
          <WorkoutSets workout={workout.data} exercises={new Map((exercises.ok ? exercises.data.items : []).map((e) => [e.id, e]))} />
        </>
      ) : (
        <LoadFailed title={w("loadFailed")} status={workout.status} />
      )}
    </div>
  );
}
