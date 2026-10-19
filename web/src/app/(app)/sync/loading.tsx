import { getTranslations } from "next-intl/server";

import { Skeleton } from "@/components/ui/skeleton";

const RUNS_PX = 220;
const CARD_PX = 200;
const CARDS = 3;

export default async function SyncLoading() {
  const t = await getTranslations("sync");
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-10 w-32" />
      <Skeleton height={RUNS_PX} className="w-full rounded-card" label={t("loading")} />
      <div className="grid gap-4 md:grid-cols-3">
        {Array.from({ length: CARDS }, (_, i) => (
          <Skeleton key={i} height={CARD_PX} className="w-full rounded-card" />
        ))}
      </div>
    </div>
  );
}
