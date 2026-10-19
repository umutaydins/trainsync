"use client";

import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { CHART_ANIMATION_MS, ChartFrame, TICK, TooltipBox, useChartAnimation } from "@/features/progress/components/chart-kit";

export interface CategoryBar {
  key: string;
  label: string;
  value: number;
  /** The value as read: `86.4 km`, `24 sets`. */
  text: string;
  /** A CSS colour (`var(--chart-1)`, `var(--muscle-chest)`). */
  fill: string;
}

const ROW_PX = 36;
const PAD_PX = 8;
const LABEL_WIDTH = 92;
/** Room right of the longest bar for its direct label. */
const VALUE_LABEL_ROOM = 72;

/** Horizontal bars with direct labels (no legend, no value axis): per sport group, per muscle. */
export function CategoryBars({
  items,
  summary,
  caption,
  columns,
  testId,
}: {
  items: readonly CategoryBar[];
  summary: string;
  caption: string;
  columns: readonly [string, string];
  testId: string;
}) {
  const animate = useChartAnimation();
  const height = items.length * ROW_PX + PAD_PX;
  return (
    <ChartFrame
      testId={testId}
      summary={summary}
      caption={caption}
      columns={columns}
      rows={items.map((item) => [item.label, item.text])}
      height={height}
    >
      <ResponsiveContainer width="100%" height={height} initialDimension={{ width: 600, height }}>
        <BarChart data={items as CategoryBar[]} layout="vertical" margin={{ top: 4, right: VALUE_LABEL_ROOM, bottom: 4, left: 0 }} barCategoryGap={8}>
          <XAxis type="number" hide domain={[0, "dataMax"]} />
          <YAxis type="category" dataKey="label" tickLine={false} axisLine={false} tick={TICK} width={LABEL_WIDTH} />
          <Tooltip
            cursor={{ fill: "var(--surface-2)" }}
            content={({ active, payload }) => {
              const item = active ? (payload?.[0]?.payload as CategoryBar | undefined) : undefined;
              return item ? <TooltipBox title={item.label}>{item.text}</TooltipBox> : null;
            }}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} isAnimationActive={animate} animationDuration={CHART_ANIMATION_MS}>
            {items.map((item) => (
              <Cell key={item.key} fill={item.fill} />
            ))}
            <LabelList dataKey="text" position="right" fill="var(--text)" fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
