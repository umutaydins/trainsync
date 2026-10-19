"use client";

import { useLocale, useTranslations } from "next-intl";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

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
import { formatBucket, formatCompact, formatDay, formatNumber } from "@/features/progress/format";
import type { Series } from "@/features/progress/types";

interface Point {
  start: string;
  label: string;
  /** null: nothing logged that day (no bar, rather than a misleading zero). */
  value: number | null;
}

/** Energy logged per day against the daily target (a dashed reference line, labelled directly). */
export function KcalChart({ series }: { series: Series }) {
  const t = useTranslations("progress.kcal");
  const locale = useLocale();
  const animate = useChartAnimation();
  const points: Point[] = series.points.map((p) => ({
    start: p.start,
    label: formatBucket(locale, p.start, series.bucket),
    value: p.value ? p.value : null,
  }));
  const logged = points.filter((p): p is Point & { value: number } => p.value != null);
  if (logged.length === 0) return <ChartEmpty>{t("empty")}</ChartEmpty>;
  const kcal = (value: number) => formatNumber(locale, value);
  const day = (start: string) => formatDay(locale, start, { weekday: "short", day: "numeric", month: "short" });
  const average = logged.reduce((sum, p) => sum + p.value, 0) / logged.length;
  const target = series.target;

  return (
    <ChartFrame
      testId="kcal-chart"
      summary={
        target == null
          ? t("summary", { count: logged.length, average: kcal(average) })
          : t("summaryTarget", { count: logged.length, average: kcal(average), target: kcal(target) })
      }
      caption={t("title")}
      columns={[t("columns.day"), t("columns.kcal")]}
      rows={logged.map((p) => [day(p.start), kcal(p.value)])}
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
                <TooltipBox title={day(point.start)}>
                  {point.value == null ? t("notLogged") : t("value", { value: kcal(point.value) })}
                </TooltipBox>
              );
            }}
          />
          <Bar
            dataKey="value"
            fill="var(--chart-1)"
            radius={[4, 4, 0, 0]}
            maxBarSize={24}
            isAnimationActive={animate}
            animationDuration={CHART_ANIMATION_MS}
          />
          {target != null ? (
            <ReferenceLine
              y={target}
              stroke="var(--muted)"
              strokeDasharray="4 4"
              ifOverflow="extendDomain"
              label={{ value: t("target", { value: kcal(target) }), position: "insideTopRight", fill: "var(--muted)", fontSize: 11 }}
            />
          ) : null}
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
