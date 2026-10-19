import { getTranslations } from "next-intl/server";

import { Skeleton } from "@/components/ui/skeleton";

const DETAIL_PX = 340;

export default async function ActivityLoading() {
  const t = await getTranslations("activities");
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <Skeleton className="h-8 w-28" />
      <Skeleton height={DETAIL_PX} className="w-full rounded-card" label={t("loading")} />
    </div>
  );
}
