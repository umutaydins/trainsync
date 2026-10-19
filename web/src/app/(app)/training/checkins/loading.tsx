import { getTranslations } from "next-intl/server";

import { Skeleton } from "@/components/ui/skeleton";

const TILES_PX = 112;
const CARD_PX = 320;

export default async function CheckinsLoading() {
  const t = await getTranslations("checkins");
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-10 w-48" label={t("loading")} />
      <Skeleton height={TILES_PX} className="w-full rounded-card" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Skeleton height={CARD_PX} className="w-full rounded-card" />
        <Skeleton height={CARD_PX} className="w-full rounded-card" />
      </div>
    </div>
  );
}
