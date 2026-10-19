import { Trophy } from "lucide-react";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import Link from "next/link";

import { Block, BlockEmpty, BlockFailure, StatGrid } from "@/features/progress/components/block";
import { E1rmChart, LIFT_CHART_ID, type Lift } from "@/features/progress/components/e1rm-chart";
import { StatCard } from "@/features/progress/components/stat-card";
import { formatNumber } from "@/features/progress/format";
import type { ExerciseStats, Period, PeriodQuery, PersonalRecord, Records } from "@/features/progress/types";
import { BETTER, progressHref } from "@/features/progress/types";
import type { Loaded } from "@/lib/api";

const KG_DIGITS = 1;
/** The list shows the newest records; the chart and its table have all of them. */
export const PR_LIST_MAX = 20;

/** Every lift with a record or a set in the period, by name. */
export function liftsOf(records: readonly PersonalRecord[], exercises: readonly ExerciseStats[]): Lift[] {
  const lifts = new Map<number, string>();
  for (const e of exercises) lifts.set(e.exercise_id, e.name);
  for (const r of records) if (!lifts.has(r.exercise_id)) lifts.set(r.exercise_id, r.name);
  return [...lifts].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * The e1RM of a lift over time with its PRs (the lift from `?lift=`, else the latest record's),
 * and the period's records, newest first.
 */
export function LiftsBlock({
  allRecords,
  periodRecords,
  exercises,
  query,
}: {
  allRecords: Loaded<Records>;
  periodRecords: Loaded<Records>;
  exercises: readonly ExerciseStats[];
  query: PeriodQuery;
}) {
  const t = useTranslations("progress.e1rm");
  const records = allRecords.ok ? allRecords.data.records : [];
  const lifts = liftsOf(records, exercises);
  const lift = lifts.find((l) => l.id === query.lift) ?? lifts.find((l) => l.id === records[0]?.exercise_id) ?? lifts[0];
  const best = exercises.find((e) => e.exercise_id === lift?.id);

  return (
    <Block id={LIFT_CHART_ID} title={t("title")} period={query.period}>
      {!allRecords.ok ? (
        <BlockFailure error={allRecords.error} />
      ) : !lift ? (
        <BlockEmpty>{t("none")}</BlockEmpty>
      ) : (
        <>
          <E1rmChart lifts={lifts} lift={lift} records={records} query={query} />
          {best ? (
            <StatGrid className="grid grid-cols-2 gap-2">
              <StatCard
                label={t("best")}
                value={best.best_e1rm_kg.value}
                digits={KG_DIGITS}
                unit={t("kg")}
                change={best.best_e1rm_kg}
                better={BETTER.tonnage}
                period={query.period}
              />
              <StatCard label={t("sets")} value={best.sets} period={query.period} />
            </StatGrid>
          ) : null}
        </>
      )}
      {periodRecords.ok ? (
        <PrList records={periodRecords.data.records} query={query} />
      ) : (
        <BlockFailure error={periodRecords.error} />
      )}
    </Block>
  );
}

/** Records of the period, newest first, each linking to its lift's chart. */
export function PrList({ records, query }: { records: readonly PersonalRecord[]; query: PeriodQuery }) {
  const t = useTranslations("progress.prs");
  const locale = useLocale();
  const format = useFormatter();
  const period: Period = query.period;
  const shown = records.slice(0, PR_LIST_MAX);
  const kg = (value: number) => formatNumber(locale, value, KG_DIGITS);
  return (
    <section aria-labelledby="pr-list-title" className="flex flex-col gap-2">
      <h3 id="pr-list-title" className="text-label font-semibold uppercase tracking-[0.08em] text-muted">
        {t("title", { count: records.length })}
      </h3>
      {shown.length === 0 ? (
        <BlockEmpty>{period === "all" ? t("emptyAll") : t("empty")}</BlockEmpty>
      ) : (
        <ol className="flex flex-col divide-y divide-border" data-testid="pr-list">
          {shown.map((record) => (
            <li key={`${record.workout_id}-${record.exercise_id}`}>
              <Link
                href={`${progressHref({ ...query, lift: record.exercise_id })}#${LIFT_CHART_ID}`}
                scroll={false}
                className="flex min-h-touch items-center gap-3 py-2.5 hover:text-accent-ink focus-visible:outline-2 focus-visible:outline-accent"
              >
                <span aria-hidden className="grid size-9 shrink-0 place-items-center rounded-full bg-accent-soft text-accent-ink">
                  <Trophy className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold">{record.name}</span>
                  <span className="block text-xs text-muted">
                    {format.dateTime(new Date(record.achieved_at), { day: "numeric", month: "short", year: "numeric" })}
                    {" · "}
                    {record.previous_kg == null ? t("first") : t("previous", { value: kg(record.previous_kg) })}
                  </span>
                </span>
                <span className="shrink-0 text-lg font-bold tabular">
                  {kg(record.e1rm_kg)} <span className="text-sm font-medium text-muted">{t("kg")}</span>
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
