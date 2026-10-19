import { useTranslations } from "next-intl";

import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { ProgressRing } from "@/components/ui/progress-ring";
import type { DaySummary } from "@/features/nutrition/types";
import { useNutritionFormat } from "@/features/nutrition/use-nutrition-format";

/*
 * Nutrition copy is neutral on purpose: numbers, targets and what is unknown, never a verdict
 * (tests/nutrition-copy.test.tsx scans every visible string for judgement words).
 */

const RING_PX = 168;
const PERCENT = 100;

function share(value: number, target: number | null): number {
  return target && target > 0 ? Math.min(1, value / target) : 0;
}

function Macro({ id, label, value, target, format }: { id: string; label: string; value: number; target: number | null; format: (v: number) => string }) {
  const t = useTranslations("nutrition.totals");
  return (
    <div className="flex flex-col gap-1" data-testid={`ring-${id}`} data-value={value} data-target={target ?? ""}>
      <p className="text-label font-semibold uppercase tracking-[0.08em] text-muted">{label}</p>
      <p className="text-xl font-bold tabular">{format(value)}</p>
      <div aria-hidden className="h-1.5 overflow-hidden rounded-full bg-surface-3">
        <div className="h-full rounded-full bg-accent" style={{ width: `${share(value, target) * PERCENT}%` }} />
      </div>
      <p className="text-xs text-muted">{target ? t("of", { target: format(target) }) : t("noTarget")}</p>
    </div>
  );
}

/** The day's kcal as a ring against the target; protein, carbs and fat as amounts (targets where set). */
export function DailyRings({ summary }: { summary: DaySummary }) {
  const t = useTranslations("nutrition.totals");
  const fmt = useNutritionFormat();
  const left = summary.kcal_remaining;
  return (
    <Card aria-labelledby="totals-title">
      <CardHeader>
        <CardTitle id="totals-title">{t("title")}</CardTitle>
      </CardHeader>
      <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center">
        <div data-testid="ring-kcal" data-value={summary.intake_kcal} data-target={summary.kcal_target ?? ""} className="shrink-0">
          <ProgressRing value={share(summary.intake_kcal, summary.kcal_target)} size={RING_PX} label={t("ringLabel")}>
            <span className="block text-label font-semibold uppercase tracking-[0.08em] text-muted">{t("energy")}</span>
            <span className="block text-2xl font-black tabular tracking-tight">{fmt.kcal(summary.intake_kcal)}</span>
            <span className="block text-xs text-muted">{summary.kcal_target ? t("of", { target: fmt.kcal(summary.kcal_target) }) : t("noTarget")}</span>
          </ProgressRing>
        </div>
        <div className="grid w-full grid-cols-3 gap-4">
          <Macro id="protein" label={t("protein")} value={summary.protein_g} target={summary.protein_target_g} format={fmt.grams} />
          <Macro id="carbs" label={t("carbs")} value={summary.carbs_g} target={null} format={fmt.grams} />
          <Macro id="fat" label={t("fat")} value={summary.fat_g} target={null} format={fmt.grams} />
        </div>
      </div>
      <div className="mt-4 flex flex-col gap-1 text-sm text-muted">
        <p data-testid="intake-kcal" data-value={summary.intake_kcal}>
          {t("intake", { kcal: fmt.kcal(summary.intake_kcal), count: summary.entry_count })}
          {left === null ? "" : ` · ${left >= 0 ? t("toTarget", { kcal: fmt.kcal(left) }) : t("aboveTarget", { kcal: fmt.kcal(-left) })}`}
        </p>
        {summary.macros_complete ? null : <p>{t("macrosIncomplete")}</p>}
      </div>
    </Card>
  );
}
