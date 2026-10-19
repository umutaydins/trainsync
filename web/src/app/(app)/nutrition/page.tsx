import type { Metadata } from "next";
import { getTimeZone, getTranslations } from "next-intl/server";

import { NutritionView } from "@/features/nutrition/components/nutrition-view";
import { loadFoodDay } from "@/features/nutrition/load";
import { localDay, localHour } from "@/features/progress/format";

export const dynamic = "force-dynamic";

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("nutrition");
  return { title: t("title") };
}

/** A valid day not after today, else today. */
function parseDate(raw: string | string[] | undefined, today: string): string {
  return typeof raw === "string" && DAY.test(raw) && !Number.isNaN(Date.parse(raw)) && raw <= today ? raw : today;
}

/** `/nutrition?date=YYYY-MM-DD`: one day of food in the user's own zone (default today). */
export default async function NutritionPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const now = new Date();
  const zone = await getTimeZone();
  const today = localDay(now, zone);
  const date = parseDate((await searchParams).date, today);
  return <NutritionView data={await loadFoodDay(date, today, localHour(now, zone))} />;
}
