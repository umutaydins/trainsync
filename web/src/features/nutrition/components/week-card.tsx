import { useTranslations } from "next-intl";

import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Stat } from "@/components/ui/stat";
import type { RangeSummary } from "@/features/nutrition/types";
import { useNutritionFormat } from "@/features/nutrition/use-nutrition-format";

const NO_VALUE = "—";

/** Week averages over the days with logged food, and the days themselves. */
export function WeeklyAverages({ weekly }: { weekly: RangeSummary }) {
  const t = useTranslations("nutrition.week");
  const balance = useTranslations("nutrition.balance");
  const fmt = useNutritionFormat();
  const logged = weekly.days.filter((d) => d.entry_count > 0);
  const avgProtein = logged.length ? logged.reduce((sum, d) => sum + d.protein_g, 0) / logged.length : null;
  const totals = weekly.totals;
  const th = "py-2 pr-3 font-semibold";
  return (
    <Card aria-labelledby="week-title">
      <CardHeader>
        <CardTitle id="week-title">{t("title")}</CardTitle>
      </CardHeader>
      <dl className="grid grid-cols-2 gap-4" data-testid="week-totals">
        <Stat label={t("avgIntake")} value={totals.avg_intake_kcal === null ? NO_VALUE : fmt.kcal(totals.avg_intake_kcal)} className="[&_span]:text-xl" />
        <Stat label={t("avgProtein")} value={avgProtein === null ? NO_VALUE : fmt.grams(avgProtein)} className="[&_span]:text-xl" />
        <Stat label={t("daysLogged")} value={t("daysOf", { logged: totals.days_logged, total: weekly.days.length })} className="[&_span]:text-xl" />
        <Stat
          label={t("balance")}
          value={totals.balance_kcal === null || !totals.balance_complete ? balance("unknown") : fmt.signedKcal(totals.balance_kcal)}
          className="[&_span]:text-xl"
        />
      </dl>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-xs tabular" data-testid="week-table">
          <caption className="sr-only">{t("caption")}</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className={th}>{t("day")}</th>
              <th scope="col" className={`${th} text-right`}>{t("intake")}</th>
              <th scope="col" className={`${th} text-right`}>{t("protein")}</th>
              <th scope="col" className={`${th} pr-0 text-right`}>{t("exercise")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {weekly.days.map((d) => (
              <tr key={d.date} data-day={d.date} data-intake={d.intake_kcal}>
                <th scope="row" className="py-2 pr-3 font-normal">{fmt.day(d.date)}</th>
                <td className="py-2 pr-3 text-right">{d.entry_count ? fmt.kcal(d.intake_kcal) : NO_VALUE}</td>
                <td className="py-2 pr-3 text-right">{d.entry_count ? fmt.grams(d.protein_g) : NO_VALUE}</td>
                <td className="py-2 text-right">{d.exercise_complete ? fmt.kcal(d.exercise_kcal) : balance("plusUnknown", { kcal: fmt.kcal(d.exercise_kcal) })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
