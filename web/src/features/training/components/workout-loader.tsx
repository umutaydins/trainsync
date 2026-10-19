"use client";

import { useTranslations } from "next-intl";
import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";
import type { Exercise, WorkoutDetail } from "@/features/training/types";

function WorkoutSkeleton() {
  const t = useTranslations("workout");
  return <Skeleton className="h-96 rounded-card" label={t("loading")} />;
}

/**
 * The workout screen reads localStorage (row client ids, the rest timer) and the clock on its
 * first render, so it renders on the client only: no server/client difference to hydrate.
 */
const WorkoutScreen = dynamic(() => import("@/features/training/components/workout-screen").then((m) => m.WorkoutScreen), {
  ssr: false,
  loading: () => <WorkoutSkeleton />,
});

export function WorkoutLoader({ initial, exercises }: { initial: WorkoutDetail; exercises: Exercise[] }) {
  return <WorkoutScreen initial={initial} exercises={exercises} />;
}
