import { useLocale, useTranslations } from "next-intl";

import { ProgressRing } from "@/components/ui/progress-ring";
import { Block, BlockEmpty, StatGrid } from "@/features/progress/components/block";
import { CategoryBars } from "@/features/progress/components/category-bars";
import { StatCard } from "@/features/progress/components/stat-card";
import { formatNumber, formatShare } from "@/features/progress/format";
import type { Adherence, Period, Strength } from "@/features/progress/types";
import { BETTER } from "@/features/progress/types";

const RING_PX = 112;
const MUSCLES = new Set(["chest", "back", "shoulders", "biceps", "triceps", "forearms", "quads", "hamstrings", "glutes", "calves", "core"]);

/** Sessions, sets, reps, tonnage and PRs; how much of the active program was done; sets per muscle. */
export function StrengthBlock({ strength, period }: { strength: Strength; period: Period }) {
  const t = useTranslations("progress.strength");
  const locale = useLocale();
  const empty = (strength.sessions.value ?? 0) === 0;
  const muscles = strength.by_muscle.filter((m) => m.sets > 0).sort((a, b) => b.sets - a.sets);
  const muscleName = (muscle: string) => (MUSCLES.has(muscle) ? t(`muscles.${muscle}`) : muscle);

  return (
    <Block id="strength" title={t("title")} period={period}>
      {empty ? (
        <BlockEmpty>{t("empty")}</BlockEmpty>
      ) : (
        <>
          <StatGrid className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <StatCard label={t("sessions")} value={strength.sessions.value} change={strength.sessions} better={BETTER.sessions} period={period} testId="stat-sessions" />
            <StatCard label={t("tonnage")} value={strength.tonnage_kg.value} unit={t("kg")} change={strength.tonnage_kg} better={BETTER.tonnage} period={period} />
            <StatCard label={t("prs")} value={strength.pr_count.value} change={strength.pr_count} better={BETTER.prs} period={period} />
            <StatCard label={t("sets")} value={strength.sets.value} change={strength.sets} better={BETTER.sets} period={period} />
            <StatCard label={t("reps")} value={strength.reps.value} change={strength.reps} better={BETTER.reps} period={period} />
          </StatGrid>
          {muscles.length > 0 ? (
            <CategoryBars
              testId="muscle-bars"
              items={muscles.map((m) => ({
                key: m.muscle,
                label: muscleName(m.muscle),
                value: m.sets,
                text: t("setCount", { count: m.sets }),
                fill: MUSCLES.has(m.muscle) ? `var(--muscle-${m.muscle})` : "var(--muted)",
              }))}
              summary={t("musclesSummary", { muscles: muscles.map((m) => `${muscleName(m.muscle)} ${formatNumber(locale, m.sets)}`).join(", ") })}
              caption={t("musclesTitle")}
              columns={[t("muscle"), t("sets")]}
            />
          ) : null}
        </>
      )}
      {strength.adherence ? <AdherenceRing adherence={strength.adherence} /> : null}
    </Block>
  );
}

function AdherenceRing({ adherence }: { adherence: Adherence }) {
  const t = useTranslations("progress.strength");
  const locale = useLocale();
  const ratio = adherence.session_ratio ?? 0;
  return (
    <div className="flex items-center gap-4 rounded-control bg-surface-2 p-3" data-testid="adherence">
      <ProgressRing value={ratio} size={RING_PX} label={t("adherenceLabel", { program: adherence.program_name, value: formatShare(locale, ratio) })}>
        <span className="text-2xl font-bold tabular">{formatShare(locale, ratio)}</span>
      </ProgressRing>
      <div className="min-w-0">
        <p className="text-label font-semibold uppercase tracking-[0.08em] text-muted">{t("adherence")}</p>
        <p className="truncate font-bold">{adherence.program_name}</p>
        <p className="text-sm text-muted">
          {t("adherenceSessions", { done: adherence.done_sessions, planned: adherence.planned_sessions })}
        </p>
        <p className="text-sm text-muted">{t("adherenceSets", { done: adherence.done_sets, planned: adherence.planned_sets })}</p>
      </div>
    </div>
  );
}
