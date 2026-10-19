import { getTranslations } from "next-intl/server";

import { Skeleton } from "@/components/ui/skeleton";

const FILTERS_PX = 72;
const TABLE_PX = 480;

export default async function ActivitiesLoading() {
  const t = await getTranslations("activities");
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-10 w-48" />
      <Skeleton height={FILTERS_PX} className="w-full rounded-card" />
      <Skeleton height={TABLE_PX} className="w-full rounded-card" label={t("loading")} />
    </div>
  );
}
