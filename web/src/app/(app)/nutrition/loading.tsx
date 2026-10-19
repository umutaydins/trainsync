import { getTranslations } from "next-intl/server";

import { Skeleton } from "@/components/ui/skeleton";

const TOTALS_PX = 220;
const BUTTON_PX = 56;
const CARD_PX = 260;

export default async function NutritionLoading() {
  const t = await getTranslations("nutrition");
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_24rem]">
      <div className="flex flex-col gap-4">
        <Skeleton className="h-10 w-40" label={t("loading")} />
        <Skeleton height={TOTALS_PX} className="w-full rounded-card" />
        <Skeleton height={BUTTON_PX} className="w-full rounded-card" />
        <Skeleton height={CARD_PX} className="w-full rounded-card" />
      </div>
      <div className="hidden flex-col gap-4 lg:flex">
        <Skeleton height={CARD_PX} className="w-full rounded-card" />
        <Skeleton height={CARD_PX} className="w-full rounded-card" />
      </div>
    </div>
  );
}
