import type { Metadata } from "next";
import { getTimeZone, getTranslations } from "next-intl/server";

import { TodayView } from "@/features/today/components/today-view";
import { loadToday } from "@/features/today/load";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("nav");
  return { title: t("today") };
}

/** `/`, the Today tab (in its own route group, so its loading skeleton is only its own). */
export default async function TodayPage() {
  return <TodayView data={await loadToday(new Date(), await getTimeZone())} />;
}
