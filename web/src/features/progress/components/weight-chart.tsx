"use client";

import { useLocale, useTranslations } from "next-intl";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

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
import { formatBucket, formatDay, formatNumber } from "@/features/progress/format";
import type { Series } from "@/features/progress/types";

const KG_DIGITS = 1;
/** Head room above and below the weights, so a flat line is not glued to the frame (kg). */
const DOMAIN_PAD_KG = 1;

interface Point {
  start: string;
  label: string;
  value: number | null;
  average: number | null;
}

/** Weigh-ins as quiet dots, the 7-day moving average as the one accent line. */
export function WeightChart({ series }: { series: Series }) {
  const t = useTranslations("progress.weight");
  const locale = useLocale();
  const animate = useChartAnimation();
  const points: Point[] = series.points.map((p) => ({
    start: p.start,
    label: formatBucket(locale, p.start, series.bucket),
    value: p.value,
    average: p.moving_average ?? null,
  }));
  const weighed = points.filter((p) => p.value != null);
  if (weighed.length === 0) return <ChartEmpty>{t("empty")}</ChartEmpty>;
  const kg = (value: number | null) => (value == null ? "—" : formatNumber(locale, value, KG_DIGITS));
  const day = (start: string) => formatDay(locale, start, { day: "numeric", month: "short", year: "numeric" });
  const hasAverage = points.some((p) => p.average != null);
  const last = weighed[weighed.length - 1];

  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="size-2 rounded-full bg-muted" />
          {t("legend.weighIns")}
        </li>
        {hasAverage ? (
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="h-0.5 w-4 rounded-full bg-chart-1" />
            {t("legend.average")}
          </li>
        ) : null}
      </ul>
      <ChartFrame
        testId="weight-chart"
        summary={t("summary", { count: weighed.length, first: kg(weighed[0]?.value ?? null), last: kg(last?.value ?? null) })}
        caption={t("title")}
        columns={[t("columns.day"), t("columns.weight"), t("columns.average")]}
        rows={weighed.map((p) => [day(p.start), kg(p.value), kg(p.average)])}
      >
        <ResponsiveContainer width="100%" height={CHART_HEIGHT} initialDimension={{ width: 600, height: CHART_HEIGHT }}>
          <LineChart data={points} margin={MARGIN}>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} tick={TICK} minTickGap={X_TICK_GAP} interval="preserveStartEnd" />
            <YAxis
              tickLine={false}
              axisLine={false}
              tick={TICK}
              width={Y_AXIS_WIDTH}
              tickCount={Y_TICKS}
              domain={[(min: number) => Math.floor(min - DOMAIN_PAD_KG), (max: number) => Math.ceil(max + DOMAIN_PAD_KG)]}
              tickFormatter={(v: number) => formatNumber(locale, v)}
            />
            <Tooltip
              cursor={{ stroke: "var(--muted)", strokeDasharray: "3 3" }}
              content={({ active, payload }) => {
                const point = active ? (payload?.[0]?.payload as Point | undefined) : undefined;
                if (!point) return null;
                return (
                  <TooltipBox title={day(point.start)}>
                    <p>{t("tooltip.weight", { value: kg(point.value) })}</p>
                    {point.average != null ? <p>{t("tooltip.average", { value: kg(point.average) })}</p> : null}
                  </TooltipBox>
                );
              }}
            />
            <Line
              dataKey="value"
              stroke="none"
              dot={{ r: 3, fill: "var(--muted)", stroke: "none" }}
              activeDot={{ r: 5, fill: "var(--muted)", stroke: "var(--surface)", strokeWidth: 2 }}
              connectNulls={false}
              isAnimationActive={animate}
              animationDuration={CHART_ANIMATION_MS}
            />
            {hasAverage ? (
              <Line
                dataKey="average"
                stroke="var(--chart-1)"
                strokeWidth={2}
                dot={false}
                connectNulls
                isAnimationActive={animate}
                animationDuration={CHART_ANIMATION_MS}
              />
            ) : null}
          </LineChart>
        </ResponsiveContainer>
      </ChartFrame>
    </div>
  );
}
