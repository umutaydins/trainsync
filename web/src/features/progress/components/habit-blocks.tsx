import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Block, BlockEmpty, StatGrid } from "@/features/progress/components/block";
import { StatCard } from "@/features/progress/components/stat-card";
import type { BodyStats, Consistency, NutritionStats, Period } from "@/features/progress/types";
import { BETTER } from "@/features/progress/types";

const PERCENT = 100;
const KG_DIGITS = 1;
const RATE_DIGITS = 2;

/** A 0..1 rate as a whole percent number (for the count-up). */
function percent(rate: number | null): number | null {
  return rate == null ? null : Math.round(rate * PERCENT);
}

/** Active days, the training streak (ISO weeks) and the check-in streak and rate. */
export function ConsistencyBlock({ consistency, period, children }: { consistency: Consistency; period: Period; children?: ReactNode }) {
  const t = useTranslations("progress.consistency");
  const c = consistency;
  return (
    <Block id="consistency" title={t("title")} period={period}>
      <StatGrid>
        <StatCard label={t("activeDays")} value={c.active_days.value} change={c.active_days} better={BETTER.activeDays} period={period} testId="stat-active-days" />
        <StatCard
          label={t("trainingStreak")}
          value={c.training_streak_weeks}
          unit={t("weeks", { count: c.training_streak_weeks })}
          hint={t("longest", { value: c.longest_training_streak_weeks })}
          period={period}
        />
        <StatCard
          label={t("checkinStreak")}
          value={c.checkin_streak_days}
          unit={t("days", { count: c.checkin_streak_days })}
          hint={t("longest", { value: c.longest_checkin_streak_days })}
          period={period}
        />
        <StatCard
          label={t("checkinRate")}
          value={percent(c.checkin_rate.value)}
          unit="%"
          change={c.checkin_rate}
          better={BETTER.checkinRate}
          period={period}
          hint={c.sick_days > 0 ? t("sickDays", { count: c.sick_days }) : undefined}
        />
      </StatGrid>
      {children}
    </Block>
  );
}

/**
 * Food over the period: numbers and targets, never a verdict (P6.7: no colour judges what was
 * eaten, every change is neutral).
 */
export function NutritionBlock({ nutrition, period, children }: { nutrition: NutritionStats; period: Period; children?: ReactNode }) {
  const t = useTranslations("progress.nutrition");
  const n = nutrition;
  const empty = (n.logged_days.value ?? 0) === 0;
  return (
    <Block id="nutrition" title={t("title")} period={period}>
      {empty ? (
        <BlockEmpty>{t("empty")}</BlockEmpty>
      ) : (
        <StatGrid>
          <StatCard
            label={t("avgKcal")}
            value={n.avg_kcal.value}
            unit={t("kcal")}
            change={n.avg_kcal}
            better={BETTER.nutrition}
            period={period}
            hint={n.kcal_target != null ? t("target", { value: n.kcal_target }) : t("noTarget")}
            testId="stat-kcal"
          />
          <StatCard label={t("protein")} value={n.avg_protein_g.value} unit={t("grams")} change={n.avg_protein_g} better={BETTER.nutrition} period={period} />
          <StatCard label={t("carbs")} value={n.avg_carbs_g.value} unit={t("grams")} change={n.avg_carbs_g} better={BETTER.nutrition} period={period} />
          <StatCard label={t("fat")} value={n.avg_fat_g.value} unit={t("grams")} change={n.avg_fat_g} better={BETTER.nutrition} period={period} />
          <StatCard
            label={t("sugarDays", { limit: n.sugar_limit_g })}
            value={n.days_over_sugar_limit.value}
            change={n.days_over_sugar_limit}
            better={BETTER.nutrition}
            period={period}
          />
          <StatCard label={t("loggingRate")} value={percent(n.logging_rate.value)} unit="%" change={n.logging_rate} better={BETTER.loggingRate} period={period} />
        </StatGrid>
      )}
      {empty ? null : children}
    </Block>
  );
}

/** Weight over the period (neutral, like food); body fat comes with Phase 9. */
export function BodyBlock({ body, period, children }: { body: BodyStats; period: Period; children?: ReactNode }) {
  const t = useTranslations("progress.body");
  const empty = body.last_kg == null;
  return (
    <Block id="body" title={t("title")} period={period}>
      {empty ? (
        <BlockEmpty>{t("empty")}</BlockEmpty>
      ) : (
        <StatGrid className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <StatCard label={t("last")} value={body.last_kg} digits={KG_DIGITS} unit={t("kg")} period={period} hint={body.first_kg != null ? t("first", { value: body.first_kg }) : undefined} testId="stat-weight" />
          <StatCard label={t("change")} value={body.change_kg.value} digits={KG_DIGITS} unit={t("kg")} change={body.change_kg} better={BETTER.weight} period={period} />
          <StatCard label={t("average")} value={body.moving_average_kg} digits={KG_DIGITS} unit={t("kg")} period={period} />
          <StatCard label={t("rate")} value={body.rate_kg_per_week.value} digits={RATE_DIGITS} unit={t("kgPerWeek")} change={body.rate_kg_per_week} better={BETTER.weight} period={period} />
          <StatCard label={t("bodyFat")} text={body.body_fat_pct == null ? null : String(body.body_fat_pct)} unit="%" period={period} hint={<Badge>{t("soon")}</Badge>} />
        </StatGrid>
      )}
      {empty ? null : children}
    </Block>
  );
}
