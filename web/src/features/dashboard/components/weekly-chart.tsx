"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatCount, formatDay, formatDuration, formatKm } from "@/lib/format";
import type { Week } from "@/lib/types";

/** Fixed chart height: the skeleton and the chart take the same box, so nothing shifts on load. */
export const CHART_HEIGHT = 260;

type Metric = "distance" | "time";

interface Point {
  week: string;
  label: string;
  value: number;
  week_data: Week;
}

export function WeeklyChart({ weeks }: { weeks: Week[] }) {
  const [metric, setMetric] = useState<Metric>("distance");
  const data: Point[] = weeks.map((w) => ({
    week: w.week_start,
    label: formatDay(w.week_start),
    value: metric === "distance" ? w.distance_m / 1000 : w.moving_time_s / 3600,
    week_data: w,
  }));

  return (
    <div>
      <div role="group" aria-label="Chart metric" className="mb-3 inline-flex rounded-lg bg-surface-2 p-0.5 text-xs">
        {(
          [
            ["distance", "Distance (km)"],
            ["time", "Time (h)"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            aria-pressed={metric === id}
            onClick={() => setMetric(id)}
            className={`rounded-md px-2.5 py-1 font-medium transition ${
              metric === id ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <div
        style={{ height: CHART_HEIGHT }}
        data-testid="weekly-chart"
        role="figure"
        aria-label={`Weekly ${metric === "distance" ? "distance in km" : "moving time in hours"}, ${weeks.length} weeks`}
      >
        <ResponsiveContainer width="100%" height={CHART_HEIGHT} initialDimension={{ width: 600, height: CHART_HEIGHT }}>
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -12 }} barCategoryGap={2}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--muted)", fontSize: 11 }}
              minTickGap={16}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--muted)", fontSize: 11 }}
              width={44}
              allowDecimals={false}
            />
            <Tooltip
              cursor={{ fill: "var(--surface-2)" }}
              content={({ active, payload }) => {
                const point = active ? (payload?.[0]?.payload as Point | undefined) : undefined;
                if (!point) return null;
                const w = point.week_data;
                return (
                  <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-md">
                    <p className="font-medium">Week of {formatDay(w.week_start, true)}</p>
                    <p className="mt-1 tabular-nums text-muted">
                      {formatKm(w.distance_m, 1)} · {formatDuration(w.moving_time_s)} · {formatCount(w.count)}{" "}
                      {w.count === 1 ? "activity" : "activities"}
                    </p>
                  </div>
                );
              }}
            />
            <Bar dataKey="value" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={36} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <WeeklyTable weeks={weeks} />
    </div>
  );
}

/** The same numbers as a table: the chart's accessible alternative. */
export function WeeklyTable({ weeks }: { weeks: Week[] }) {
  return (
    <details className="mt-3 text-sm">
      <summary className="cursor-pointer text-xs font-medium text-muted hover:text-text">Show weekly data</summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-left text-xs tabular-nums" data-testid="weekly-table">
          <caption className="sr-only">Weekly totals</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1.5 pr-3 font-medium">Week of</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">Activities</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">Distance</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">Moving time</th>
              <th scope="col" className="py-1.5 text-right font-medium">Elevation</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {weeks.map((w) => (
              <tr key={w.week_start} data-week={w.week_start} data-count={w.count} data-distance={w.distance_m}>
                <th scope="row" className="py-1.5 pr-3 font-normal">{formatDay(w.week_start, true)}</th>
                <td className="py-1.5 pr-3 text-right">{formatCount(w.count)}</td>
                <td className="py-1.5 pr-3 text-right">{formatKm(w.distance_m, 1)}</td>
                <td className="py-1.5 pr-3 text-right">{formatDuration(w.moving_time_s)}</td>
                <td className="py-1.5 text-right">{Math.round(w.elevation_gain_m)} m</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
