import { getTranslations } from "next-intl/server";

import { Skeleton } from "@/components/ui/skeleton";

const SUMMARY_PX = 120;
const SETS_PX = 240;

export default async function WorkoutDetailLoading() {
  const t = await getTranslations("workout");
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <Skeleton className="h-8 w-28" />
      <Skeleton className="h-10 w-56" label={t("loading")} />
      <Skeleton height={SUMMARY_PX} className="w-full rounded-card" />
      <Skeleton height={SETS_PX} className="w-full rounded-card" />
    </div>
  );
}
