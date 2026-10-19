import { useTranslations } from "next-intl";

import { PageTitle } from "@/components/ui/page-header";
import { LoadFailed } from "@/features/shell/components/load-failed";
import { AddFood } from "@/features/nutrition/components/add-food";
import { EnergyBalanceCard } from "@/features/nutrition/components/balance-card";
import { DayNav } from "@/features/nutrition/components/day-nav";
import { MealList } from "@/features/nutrition/components/meal-list";
import { ProfileForm } from "@/features/nutrition/components/profile-form";
import { DailyRings } from "@/features/nutrition/components/totals-card";
import { WeeklyAverages } from "@/features/nutrition/components/week-card";
import type { FoodDay } from "@/features/nutrition/load";
import { useNutritionFormat } from "@/features/nutrition/use-nutrition-format";

/** `/nutrition`, the Food tab: the day's totals, add food, meals; balance, week and profile beside. */
export function NutritionView({ data }: { data: FoodDay }) {
  const t = useTranslations("nutrition");
  const fmt = useNutritionFormat();
  const { date, summary, log, weekly } = data;
  const day = fmt.day(date, true);
  return (
    <div data-testid="nutrition-day" data-date={date}>
      <PageTitle title={t("title")} subtitle={date === data.today ? t("dayToday", { date: day }) : day} aside={<DayNav date={date} today={data.today} />} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_24rem]">
        <div className="flex min-w-0 flex-col gap-4">
          {summary.ok ? <DailyRings summary={summary.data} /> : <LoadFailed title={t("failed.totals")} status={summary.status} />}
          <AddFood key={date} date={date} favorites={data.favorites} recent={data.recent} defaultMeal={data.defaultMeal} />
          {log.ok ? <MealList entries={log.data.entries} /> : <LoadFailed title={t("failed.log")} status={log.status} />}
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          {summary.ok ? <EnergyBalanceCard summary={summary.data} /> : null}
          {weekly.ok ? <WeeklyAverages weekly={weekly.data} /> : <LoadFailed title={t("failed.week")} status={weekly.status} />}
          <ProfileForm profile={data.profile} date={date} />
        </div>
      </div>
    </div>
  );
}
