import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { trainingApi } from "@/features/training/api";
import { TrainingHome } from "@/features/training/components/training-home";
import { load } from "@/lib/api";

export const dynamic = "force-dynamic";

/** Open workouts are among the latest few. */
const RECENT_WORKOUTS = 10;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("training");
  return { title: t("title") };
}

export default async function TrainingPage() {
  const [program, workouts] = await Promise.all([load(() => trainingApi.activeProgram()), load(() => trainingApi.workouts(RECENT_WORKOUTS))]);
  return <TrainingHome program={program} workouts={workouts} />;
}
