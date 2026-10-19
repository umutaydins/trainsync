import { getTranslations } from "next-intl/server";

import { Skeleton } from "@/components/ui/skeleton";

const CHART_PX = 320;

export default async function LiftsLoading() {
  const t = await getTranslations("training.lifts");
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-10 w-40" label={t("loading")} />
      <Skeleton height={CHART_PX} className="w-full rounded-card" />
      <Skeleton height={CHART_PX} className="w-full rounded-card" />
    </div>
  );
}
