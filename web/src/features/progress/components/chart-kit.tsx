"use client";

import { useReducedMotion } from "motion/react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

/** Every progress chart takes this box; the skeletons reserve the same, so nothing shifts. */
export const CHART_HEIGHT = 220;
/** Recharts animates a period change this long (ms), unless the user asked for less motion. */
export const CHART_ANIMATION_MS = 450;
/** Few ticks: a phone-wide axis stays readable. */
export const Y_TICKS = 4;
export const X_TICK_GAP = 28;
export const Y_AXIS_WIDTH = 40;
export const TICK = { fill: "var(--muted)", fontSize: 11 } as const;
export const GRID = "var(--chart-grid)";
export const MARGIN = { top: 8, right: 8, bottom: 0, left: 0 } as const;

/** Whether charts animate (reduced motion: no). */
export function useChartAnimation(): boolean {
  return !useReducedMotion();
}

/**
 * A chart with its accessible summary (`aria-label`, one sentence) and the same numbers as a
 * table behind "Show data" (screen readers, and anyone who wants the exact values).
 */
export function ChartFrame({
  summary,
  caption,
  columns,
  rows,
  height = CHART_HEIGHT,
  testId,
  children,
}: {
  summary: string;
  caption: string;
  columns: readonly string[];
  rows: readonly (readonly string[])[];
  height?: number;
  testId?: string;
  children: ReactNode;
}) {
  const t = useTranslations("progress.chart");
  return (
    <figure className="m-0" aria-label={summary} data-testid={testId}>
      <div style={{ height }} className="w-full select-none">
        {children}
      </div>
      <details className="mt-2 text-sm">
        <summary className="inline-flex h-touch cursor-pointer items-center text-xs font-semibold text-muted hover:text-text">
          {t("showData")}
        </summary>
        <div className="max-h-64 overflow-auto">
          <table className="w-full text-left text-xs tabular">
            <caption className="sr-only">{caption}</caption>
            <thead className="text-muted">
              <tr>
                {columns.map((column, index) => (
                  <th key={column} scope="col" className={index === 0 ? "py-1.5 pr-3 font-medium" : "py-1.5 pl-3 text-right font-medium"}>
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map(([head, ...cells], index) => (
                <tr key={`${head}-${index}`}>
                  <th scope="row" className="py-1.5 pr-3 font-normal">
                    {head}
                  </th>
                  {cells.map((cell, cellIndex) => (
                    <td key={cellIndex} className="py-1.5 pl-3 text-right">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

/** The tooltip box of every chart (tap a bar or a point on a phone). */
export function TooltipBox({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <div className="rounded-control border border-border bg-surface px-3 py-2 text-xs shadow-float">
      <p className="font-semibold">{title}</p>
      <div className="mt-0.5 tabular text-muted">{children}</div>
    </div>
  );
}

/** A chart block with nothing to draw: a quiet line in the chart's own box. */
export function ChartEmpty({ children, height = CHART_HEIGHT }: { children: ReactNode; height?: number }) {
  return (
    <div style={{ height }} className="grid place-items-center rounded-control border border-dashed border-border px-6 text-center text-sm text-muted">
      {children}
    </div>
  );
}
