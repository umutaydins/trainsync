import { getTranslations } from "next-intl/server";

import { TodaySkeleton } from "@/features/today/components/today-skeleton";

export default async function TodayLoading() {
  const t = await getTranslations("today");
  return <TodaySkeleton label={t("loading")} />;
}
