"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Segmented } from "@/components/ui/segmented";
import {
  CHART_ANIMATION_MS,
  CHART_HEIGHT,
  ChartEmpty,
  ChartFrame,
  GRID,
  MARGIN,
  TICK,
  TooltipBox,
  X_TICK_GAP,
  Y_AXIS_WIDTH,
  Y_TICKS,
  useChartAnimation,
} from "@/features/progress/components/chart-kit";
import { formatBucket, formatCompact, formatDay, formatNumber, km } from "@/features/progress/format";
import type { Series } from "@/features/progress/types";

type VolumeMetric = "distance" | "tonnage";

interface Point {
  start: string;
  label: string;
  value: number;
}

const TONNAGE_DIGITS = 0;
const KM_DIGITS = 1;

/** Endurance distance or lifted tonnage per bucket of the period (two charts in one card, one axis). */
export function VolumeChart({ distance, tonnage }: { distance: Series | null; tonnage: Series | null }) {
  const t = useTranslations("progress.volume");
  const locale = useLocale();
  const animate = useChartAnimation();
  const [metric, setMetric] = useState<VolumeMetric>(distance ? "distance" : "tonnage");
  const series = metric === "distance" ? distance : tonnage;
  const unit = t(`unit.${metric}`);
  const digits = metric === "distance" ? KM_DIGITS : TONNAGE_DIGITS;
  const points: Point[] = (series?.points ?? []).map((p) => ({
    start: p.start,
    label: formatBucket(locale, p.start, series?.bucket ?? "day"),
    value: metric === "distance" ? km(p.value ?? 0) : (p.value ?? 0),
  }));
  const total = points.reduce((sum, p) => sum + p.value, 0);
  const options = (["distance", "tonnage"] as const)
    .filter((m) => (m === "distance" ? distance : tonnage))
    .map((m) => ({ value: m, label: t(`metric.${m}`) }));
  const bucket = series?.bucket ?? "day";
  /** A bucket in words: the day itself, "Week of 12 Oct", or the month. */
  const when = (start: string) =>
    bucket === "day"
      ? formatDay(locale, start, { weekday: "short", day: "numeric", month: "short" })
      : t(`bucket.${bucket}`, { start: formatBucket(locale, start, bucket) });

  return (
    <div className="flex flex-col gap-3">
      {options.length > 1 ? <Segmented value={metric} options={options} onChange={setMetric} label={t("metricLabel")} className="max-w-xs" /> : null}
      {total === 0 ? (
        <ChartEmpty>{t(`empty.${metric}`)}</ChartEmpty>
      ) : (
        <ChartFrame
          testId="volume-chart"
          summary={t("summary", { metric: t(`metric.${metric}`), total: formatNumber(locale, total, digits), unit, count: points.length })}
          caption={t(`metric.${metric}`)}
          columns={[t("columns.when"), `${t(`metric.${metric}`)} (${unit})`]}
          rows={points.map((p) => [when(p.start), formatNumber(locale, p.value, digits)])}
        >
          <ResponsiveContainer width="100%" height={CHART_HEIGHT} initialDimension={{ width: 600, height: CHART_HEIGHT }}>
            <BarChart data={points} margin={MARGIN} barCategoryGap="12%">
              <CartesianGrid vertical={false} stroke={GRID} />
              <XAxis dataKey="label" tickLine={false} axisLine={false} tick={TICK} minTickGap={X_TICK_GAP} interval="preserveStartEnd" />
              <YAxis
                tickLine={false}
                axisLine={false}
                tick={TICK}
                width={Y_AXIS_WIDTH}
                tickCount={Y_TICKS}
                tickFormatter={(v: number) => formatCompact(locale, v)}
              />
              <Tooltip
                cursor={{ fill: "var(--surface-2)" }}
                content={({ active, payload }) => {
                  const point = active ? (payload?.[0]?.payload as Point | undefined) : undefined;
                  if (!point) return null;
                  return (
                    <TooltipBox title={when(point.start)}>
                      {formatNumber(locale, point.value, digits)} {unit}
                    </TooltipBox>
                  );
                }}
              />
              <Bar
                dataKey="value"
                fill="var(--chart-1)"
                radius={[4, 4, 0, 0]}
                maxBarSize={28}
                isAnimationActive={animate}
                animationDuration={CHART_ANIMATION_MS}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      )}
    </div>
  );
}
