import { getTranslations } from "next-intl/server";

import { Skeleton } from "@/components/ui/skeleton";

const ROWS = 6;
const ROW_PX = 64;

export default async function HistoryLoading() {
  const t = await getTranslations("training.history");
  return (
    <div className="flex flex-col gap-3">
      <Skeleton className="h-10 w-40" label={t("loading")} />
      {Array.from({ length: ROWS }, (_, i) => (
        <Skeleton key={i} height={ROW_PX} className="w-full rounded-card" />
      ))}
    </div>
  );
}
