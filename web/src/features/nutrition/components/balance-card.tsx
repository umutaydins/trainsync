import { useTranslations } from "next-intl";

import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import type { DaySummary } from "@/features/nutrition/types";
import { useNutritionFormat } from "@/features/nutrition/use-nutrition-format";

function Row({ label, value, note, testId }: { label: string; value: string; note?: string; testId: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2.5" data-testid={testId}>
      <dt className="text-sm font-medium">
        {label}
        {note ? <span className="block text-xs font-normal text-muted">{note}</span> : null}
      </dt>
      <dd className="text-right font-bold tabular">{value}</dd>
    </div>
  );
}

/**
 * Intake against an *estimated* expenditure (ADR 0019). Every estimate says so; anything the API
 * could not compute, or computed without some activities' energy, shows as "unknown", never a guess.
 */
export function EnergyBalanceCard({ summary }: { summary: DaySummary }) {
  const t = useTranslations("nutrition.balance");
  const fmt = useNutritionFormat();
  const unknown = t("unknown");
  const exerciseNote =
    summary.exercise_unknown_count > 0
      ? t("exerciseUnknown", { count: summary.exercise_unknown_count })
      : summary.activities.length === 0
        ? t("exerciseNone")
        : t("exerciseFrom", { count: summary.activities.length });
  const expenditureKnown = summary.expenditure_kcal !== null && summary.exercise_complete;
  const balanceKnown = summary.balance_kcal !== null && summary.balance_complete;
  return (
    <Card aria-labelledby="balance-title">
      <CardHeader>
        <CardTitle id="balance-title">{t("title")}</CardTitle>
      </CardHeader>
      <dl className="divide-y divide-border" data-testid="energy-balance">
        <Row testId="row-intake" label={t("intake")} note={t("intakeNote")} value={fmt.kcal(summary.intake_kcal)} />
        <Row testId="row-bmr" label={t("bmr")} note={t("bmrNote")} value={summary.bmr_kcal === null ? unknown : fmt.kcal(summary.bmr_kcal)} />
        <Row
          testId="row-baseline"
          label={t("baseline")}
          note={summary.activity_baseline ? t("baselineNoteWith", { level: t(`levels.${summary.activity_baseline}`) }) : t("baselineNote")}
          value={summary.baseline_kcal === null ? unknown : fmt.kcal(summary.baseline_kcal)}
        />
        <Row
          testId="row-exercise"
          label={t("exercise")}
          note={exerciseNote}
          value={summary.exercise_complete ? fmt.kcal(summary.exercise_kcal) : t("plusUnknown", { kcal: fmt.kcal(summary.exercise_kcal) })}
        />
        <Row testId="row-expenditure" label={t("expenditure")} note={t("estimate")} value={expenditureKnown ? fmt.kcal(summary.expenditure_kcal ?? 0) : unknown} />
        <Row testId="row-balance" label={t("balance")} note={t("balanceNote")} value={balanceKnown ? fmt.signedKcal(summary.balance_kcal ?? 0) : unknown} />
      </dl>
      {summary.estimate_unavailable_reason ? <p className="mt-3 text-xs text-muted">{t(`gaps.${summary.estimate_unavailable_reason}`)}</p> : null}
      {!summary.exercise_complete ? <p className="mt-3 text-xs text-muted">{t("stravaGap")}</p> : null}
    </Card>
  );
}
