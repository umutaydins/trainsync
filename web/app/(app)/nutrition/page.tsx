import type { Metadata } from "next";
import Link from "next/link";

import { AddFood } from "@/components/nutrition/add-food";
import { MealList } from "@/components/nutrition/meal-list";
import { ProfileForm } from "@/components/nutrition/profile-form";
import { DailyRings, EnergyBalanceCard, WeeklyAverages } from "@/components/nutrition/summary-cards";
import { ErrorState, PageHeader } from "@/components/ui";
import { load } from "@/lib/api";
import { formatDay } from "@/lib/format";
import { nutritionApi } from "@/lib/nutrition-api";
import type { Food } from "@/lib/nutrition-types";
import { addDays, utcToday, weekStart } from "@/lib/nutrition-types";

export const metadata: Metadata = { title: "Nutrition" };
export const dynamic = "force-dynamic";

const RECENT_DAYS = 3;

function parseDate(raw: string | string[] | undefined, today: string): string {
  return typeof raw === "string" && /^\d{4}-\d{2}-\d{2}$/.test(raw) && !Number.isNaN(Date.parse(raw)) ? raw : today;
}

/** `/nutrition?date=YYYY-MM-DD` (UTC day, default today): meals, add food, totals, balance, week. */
export default async function NutritionPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const today = utcToday();
  const date = parseDate((await searchParams).date, today);
  const monday = weekStart(date);
  const [summary, log, weekly, favorites, profile, ...previous] = await Promise.all([
    load(() => nutritionApi.summary(date)),
    load(() => nutritionApi.log(date)),
    load(() => nutritionApi.weekly(monday, addDays(monday, 6))),
    load(() => nutritionApi.favorites()),
    load(() => nutritionApi.profile()),
    ...Array.from({ length: RECENT_DAYS }, (_, i) => load(() => nutritionApi.log(addDays(date, -i)))),
  ]);

  // Recent: distinct foods of the last few days' logs, newest first.
  const recent = new Map<number, Food>();
  for (const day of previous) {
    if (!day.ok) continue;
    for (const e of [...day.data.entries].reverse()) {
      if (!recent.has(e.food_id)) {
        recent.set(e.food_id, {
          id: e.food_id,
          name: e.food_name,
          brand: e.brand,
          barcode: null,
          kcal_100g: e.grams > 0 ? Math.round((e.kcal / e.grams) * 1000) / 10 : 0,
          protein_100g: e.protein_g === null || e.grams <= 0 ? null : Math.round((e.protein_g / e.grams) * 1000) / 10,
          carbs_100g: e.carbs_g === null || e.grams <= 0 ? null : Math.round((e.carbs_g / e.grams) * 1000) / 10,
          fat_100g: e.fat_g === null || e.grams <= 0 ? null : Math.round((e.fat_g / e.grams) * 1000) / 10,
          source: "manual",
          favorite: false,
        });
      }
    }
  }

  return (
    <>
      <PageHeader
        title="Nutrition"
        subtitle={`${formatDay(date, true)}${date === today ? " · today" : ""} (UTC day)`}
        aside={
          <nav aria-label="Day" className="flex gap-1 text-sm">
            <Link href={`/nutrition?date=${addDays(date, -1)}`} className="inline-flex min-h-11 items-center rounded-lg px-3 hover:bg-surface-2">
              ← Previous day
            </Link>
            {date !== today ? (
              <Link href="/nutrition" className="inline-flex min-h-11 items-center rounded-lg px-3 hover:bg-surface-2">
                Today
              </Link>
            ) : null}
            {date < today ? (
              <Link href={`/nutrition?date=${addDays(date, 1)}`} className="inline-flex min-h-11 items-center rounded-lg px-3 hover:bg-surface-2">
                Next day →
              </Link>
            ) : null}
          </nav>
        }
      />
      <div className="grid gap-4 lg:grid-cols-[1fr_24rem]" data-testid="nutrition-day" data-date={date}>
        <div className="min-w-0 space-y-4">
          {summary.ok ? <DailyRings summary={summary.data} /> : <ErrorState title="Could not load the day’s totals" message={summary.error} />}
          {log.ok ? <MealList entries={log.data.entries} /> : <ErrorState title="Could not load the food log" message={log.error} />}
          <AddFood key={date} date={date} favorites={favorites.ok ? favorites.data.items : []} recent={[...recent.values()].slice(0, 10)} />
        </div>
        <div className="min-w-0 space-y-4">
          {summary.ok ? <EnergyBalanceCard summary={summary.data} /> : null}
          {weekly.ok ? <WeeklyAverages weekly={weekly.data} /> : <ErrorState title="Could not load the week" message={weekly.error} />}
          <ProfileForm profile={profile.ok ? profile.data : null} date={date} />
        </div>
      </div>
    </>
  );
}
