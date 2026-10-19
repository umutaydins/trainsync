import { useLocale, useTranslations } from "next-intl";

import { Block, BlockEmpty, StatGrid } from "@/features/progress/components/block";
import { CategoryBars } from "@/features/progress/components/category-bars";
import { StatCard } from "@/features/progress/components/stat-card";
import { effortUnit, formatDuration, formatEffort, formatNumber, km, paceChangePct } from "@/features/progress/format";
import type { Endurance, Period, SportGroupStats } from "@/features/progress/types";
import { BETTER } from "@/features/progress/types";

const KM_DIGITS = 1;

/** Distance, time, elevation and activities of the period, then each sport group on its own. */
export function EnduranceBlock({ endurance, period }: { endurance: Endurance; period: Period }) {
  const t = useTranslations("progress.endurance");
  const locale = useLocale();
  const { totals } = endurance;
  const groups = endurance.by_group.filter((g) => (g.count.value ?? 0) > 0);
  const empty = (totals.count.value ?? 0) === 0;

  return (
    <Block id="endurance" title={t("title")} period={period}>
      {empty ? (
        <BlockEmpty>{t("empty")}</BlockEmpty>
      ) : (
        <>
          <StatGrid>
            <StatCard label={t("distance")} value={km(totals.distance_m.value ?? 0)} digits={KM_DIGITS} unit={t("km")} change={totals.distance_m} better={BETTER.distance} period={period} testId="stat-distance" />
            <StatCard label={t("time")} text={formatDuration(totals.moving_time_s.value ?? 0)} unit={t("hours")} change={totals.moving_time_s} better={BETTER.time} period={period} />
            <StatCard label={t("elevation")} value={totals.elevation_gain_m.value} unit={t("meters")} change={totals.elevation_gain_m} better={BETTER.elevation} period={period} />
            <StatCard label={t("count")} value={totals.count.value} change={totals.count} better={BETTER.count} period={period} testId="stat-activities" />
          </StatGrid>
          <ul className="flex flex-col gap-3">
            {groups.map((group) => (
              <GroupRow key={group.group} group={group} period={period} />
            ))}
          </ul>
          {groups.length > 1 ? (
            <CategoryBars
              testId="sport-bars"
              items={groups.map((g, index) => ({
                key: g.group,
                label: t(`groups.${g.group}`),
                value: km(g.distance_m.value ?? 0),
                text: `${formatNumber(locale, km(g.distance_m.value ?? 0), KM_DIGITS)} ${t("km")}`,
                fill: index === 0 ? "var(--chart-1)" : "var(--muted)",
              }))}
              summary={t("barsSummary", {
                groups: groups.map((g) => `${t(`groups.${g.group}`)} ${formatNumber(locale, km(g.distance_m.value ?? 0), KM_DIGITS)} ${t("km")}`).join(", "),
              })}
              caption={t("barsTitle")}
              columns={[t("group"), t("distance")]}
            />
          ) : null}
        </>
      )}
    </Block>
  );
}

function GroupRow({ group, period }: { group: SportGroupStats; period: Period }) {
  const t = useTranslations("progress.endurance");
  const locale = useLocale();
  const unit = effortUnit(group.group);
  const pace = unit !== "kmh";
  return (
    <li className="rounded-control border border-border p-3" data-group={group.group}>
      <p className="mb-2 flex items-baseline justify-between gap-2">
        <span className="font-bold">{t(`groups.${group.group}`)}</span>
        <span className="text-xs text-muted">{t("activities", { count: group.count.value ?? 0 })}</span>
      </p>
      <StatGrid className="grid grid-cols-3 gap-2">
        <StatCard label={t("distance")} value={km(group.distance_m.value ?? 0)} digits={KM_DIGITS} unit={t("km")} change={group.distance_m} better={BETTER.distance} period={period} />
        <StatCard
          label={pace ? t("pace") : t("speed")}
          text={formatEffort(locale, group.group, group.average_speed_mps.value)}
          unit={t(`effort.${unit}`)}
          pct={pace ? paceChangePct(group.average_speed_mps) : group.average_speed_mps.change_pct}
          better={pace ? BETTER.pace : BETTER.speed}
          period={period}
        />
        <StatCard label={t("heartrate")} value={group.average_heartrate.value} unit={t("bpm")} change={group.average_heartrate} better={BETTER.heartrate} period={period} />
      </StatGrid>
    </li>
  );
}
