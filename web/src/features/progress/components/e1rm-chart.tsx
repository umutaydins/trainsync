"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Field } from "@/components/ui/field";
import { BlockEmpty } from "@/features/progress/components/block";
import { Select } from "@/components/ui/input";
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
import { formatNumber } from "@/features/progress/format";
import type { PeriodQuery, PersonalRecord } from "@/features/progress/types";
import { progressHref } from "@/features/progress/types";

export interface Lift {
  id: number;
  name: string;
}

interface Point {
  time: number;
  e1rm: number;
  previous: number | null;
}

const KG_DIGITS = 1;
const DOMAIN_PAD_KG = 5;
export const LIFT_CHART_ID = "lift-chart";

/**
 * Records of one lift over its whole history: a step line (a record holds until it is beaten)
 * with a marker on every PR. The lift picker lives in the URL (`?lift=`), so a PR links here.
 */
export function E1rmChart({
  lifts,
  lift,
  records,
  query,
}: {
  lifts: readonly Lift[];
  lift: Lift;
  /** Every PR of every lift, newest first (`/v1/stats/prs?period=all`). */
  records: readonly PersonalRecord[];
  query: PeriodQuery;
}) {
  const t = useTranslations("progress.e1rm");
  const locale = useLocale();
  const router = useRouter();
  const animate = useChartAnimation();
  const points: Point[] = records
    .filter((r) => r.exercise_id === lift.id)
    .map((r) => ({ time: Date.parse(r.achieved_at), e1rm: r.e1rm_kg, previous: r.previous_kg }))
    .sort((a, b) => a.time - b.time);
  const kg = (value: number) => formatNumber(locale, value, KG_DIGITS);
  const format = useFormatter();
  const date = (time: number, year: "numeric" | "2-digit" = "numeric") => format.dateTime(time, { day: "numeric", month: "short", year });
  const best = points[points.length - 1];

  return (
    <div className="flex flex-col gap-3">
      {lifts.length > 1 ? (
        <Field label={t("pick")} className="max-w-xs">
          <Select
            value={lift.id}
            onChange={(event) => router.replace(`${progressHref({ ...query, lift: Number(event.target.value) })}#${LIFT_CHART_ID}`, { scroll: false })}
          >
            {lifts.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </Select>
        </Field>
      ) : null}
      {points.length === 0 || !best ? (
        <ChartEmpty>{t("empty", { lift: lift.name })}</ChartEmpty>
      ) : points.length < 2 ? (
        // One dot is no trend: say what it is in a line instead of drawing a near-empty chart.
        <BlockEmpty testId="e1rm-single">{t("single", { lift: lift.name, value: kg(best.e1rm), date: date(best.time) })}</BlockEmpty>
      ) : (
        <ChartFrame
          testId="e1rm-chart"
          summary={t("summary", { lift: lift.name, count: points.length, best: kg(best.e1rm), date: date(best.time) })}
          caption={t("caption", { lift: lift.name })}
          columns={[t("columns.date"), t("columns.e1rm"), t("columns.previous")]}
          rows={[...points].reverse().map((p) => [date(p.time), kg(p.e1rm), p.previous == null ? t("first") : kg(p.previous)])}
        >
          <ResponsiveContainer width="100%" height={CHART_HEIGHT} initialDimension={{ width: 600, height: CHART_HEIGHT }}>
            <LineChart data={points} margin={MARGIN}>
              <CartesianGrid vertical={false} stroke={GRID} />
              <XAxis
                dataKey="time"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickLine={false}
                axisLine={false}
                tick={TICK}
                minTickGap={X_TICK_GAP}
                tickFormatter={(v: number) => date(v, "2-digit")}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                tick={TICK}
                width={Y_AXIS_WIDTH}
                tickCount={Y_TICKS}
                domain={[(min: number) => Math.max(0, Math.floor(min - DOMAIN_PAD_KG)), (max: number) => Math.ceil(max + DOMAIN_PAD_KG)]}
                tickFormatter={(v: number) => formatNumber(locale, v)}
              />
              <Tooltip
                cursor={{ stroke: "var(--muted)", strokeDasharray: "3 3" }}
                content={({ active, payload }) => {
                  const point = active ? (payload?.[0]?.payload as Point | undefined) : undefined;
                  if (!point) return null;
                  return (
                    <TooltipBox title={date(point.time)}>
                      <p>{t("tooltip", { value: kg(point.e1rm) })}</p>
                      <p>{point.previous == null ? t("first") : t("beat", { value: kg(point.previous) })}</p>
                    </TooltipBox>
                  );
                }}
              />
              <Line
                type="stepAfter"
                dataKey="e1rm"
                stroke="var(--chart-1)"
                strokeWidth={2}
                dot={{ r: 5, fill: "var(--chart-1)", stroke: "var(--surface)", strokeWidth: 2 }}
                activeDot={{ r: 7, fill: "var(--chart-1)", stroke: "var(--surface)", strokeWidth: 2 }}
                isAnimationActive={animate}
                animationDuration={CHART_ANIMATION_MS}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartFrame>
      )}
    </div>
  );
}
