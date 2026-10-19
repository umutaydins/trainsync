import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { trainingApi } from "@/features/training/api";
import { LiftsView } from "@/features/training/components/lifts-view";
import { load } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("training.lifts");
  return { title: t("title") };
}

/** `/training/progress?exercise=<id>`: shareable, rendered on the server. */
export default async function LiftsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
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
  const ordered = [...list.filter((e) => trained.includes(e.id)), ...list.filter((e) => !trained.includes(e.id))];
  return <LiftsView data={{ exercises: ordered, exerciseId, progress, records, weekly, weights }} />;
}
