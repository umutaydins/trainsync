import { getTranslations } from "next-intl/server";

import { Skeleton } from "@/components/ui/skeleton";

const DAY_PX = 96;
const DAYS = 3;

export default async function TrainingLoading() {
  const t = await getTranslations("training");
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-10 w-40" label={t("loading")} />
      <div className="flex flex-col gap-3 rounded-card border border-border bg-surface p-4">
        <Skeleton className="h-7 w-56" />
        {Array.from({ length: DAYS }, (_, i) => (
          <Skeleton key={i} height={DAY_PX} className="w-full rounded-card" />
        ))}
      </div>
    </div>
  );
}
