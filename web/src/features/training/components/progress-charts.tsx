"use client";

import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatDate, formatDay } from "@/lib/format";
import type { BodyMetric, ExerciseProgress, MuscleWeek } from "@/features/training/types";
import { formatKg, formatVolume, label } from "@/features/training/types";

export const PROGRESS_CHART_HEIGHT = 240;

const AXIS = { tickLine: false, axisLine: false, tick: { fill: "var(--muted)", fontSize: 11 } } as const;

/** Muscle colours for the stacked bars, fixed per muscle so a week-to-week comparison holds. */
export const MUSCLE_COLORS: Record<string, string> = {
  chest: "var(--muscle-chest)",
  back: "var(--muscle-back)",
  shoulders: "var(--muscle-shoulders)",
  biceps: "var(--muscle-biceps)",
  triceps: "var(--muscle-triceps)",
  forearms: "var(--muscle-forearms)",
  quads: "var(--muscle-quads)",
  hamstrings: "var(--muscle-hamstrings)",
  glutes: "var(--muscle-glutes)",
  calves: "var(--muscle-calves)",
  core: "var(--muscle-core)",
};

function Details({ summary, children }: { summary: string; children: React.ReactNode }) {
  return (
    <details className="mt-3 text-sm">
      <summary className="cursor-pointer text-xs font-medium text-muted hover:text-text">{summary}</summary>
      <div className="mt-2 overflow-x-auto">{children}</div>
    </details>
  );
}

/** e1RM and best-set weight per workout for one exercise, oldest first. */
export function ExerciseProgressChart({ progress }: { progress: ExerciseProgress }) {
  const data = progress.sessions.map((s) => ({
    label: formatDate(s.started_at),
    e1rm: s.e1rm_kg,
    best: s.best_set?.weight_kg ?? null,
  }));
  return (
    <div>
      <div style={{ height: PROGRESS_CHART_HEIGHT }} role="figure" aria-label={`${progress.exercise.name}: e1RM and best set per workout`} data-testid="exercise-chart">
        <ResponsiveContainer width="100%" height={PROGRESS_CHART_HEIGHT} initialDimension={{ width: 600, height: PROGRESS_CHART_HEIGHT }}>
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis dataKey="label" {...AXIS} minTickGap={16} />
            <YAxis {...AXIS} width={44} />
            <Tooltip formatter={(v) => (typeof v === "number" ? formatKg(v, 1) : String(v))} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="e1rm" name="e1RM" stroke="var(--chart-1)" strokeWidth={2} dot={{ r: 3 }} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="best" name="Best set kg" stroke="var(--chart-2)" strokeWidth={2} dot={{ r: 3 }} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <Details summary="Show sessions">
        <table className="w-full text-left text-xs tabular-nums" data-testid="exercise-table">
          <caption className="sr-only">{progress.exercise.name} per workout</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1.5 pr-3 font-medium">Workout</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">Best set</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">e1RM</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">Volume</th>
              <th scope="col" className="py-1.5 text-right font-medium">Sets</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {progress.sessions.map((s) => (
              <tr
                key={s.workout_id}
                data-workout={s.workout_id}
                data-best-weight={s.best_set?.weight_kg ?? ""}
                data-best-reps={s.best_set?.reps ?? ""}
                data-e1rm={s.e1rm_kg ?? ""}
                data-volume={s.volume_kg}
              >
                <th scope="row" className="py-1.5 pr-3 font-normal">{formatDate(s.started_at)}</th>
                <td className="py-1.5 pr-3 text-right">{s.best_set ? `${s.best_set.reps} × ${formatKg(s.best_set.weight_kg)}` : "—"}</td>
                <td className="py-1.5 pr-3 text-right">{s.e1rm_kg !== null ? formatKg(s.e1rm_kg, 1) : "—"}</td>
                <td className="py-1.5 pr-3 text-right">{formatVolume(s.volume_kg)}</td>
                <td className="py-1.5 text-right">{s.working_sets}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Details>
    </div>
  );
}

export interface WeekRow {
  week: string;
  total: number;
  [muscle: string]: number | string;
}

/** API items (week × muscle) → one row per week with a kg column per muscle. */
export function pivotWeeks(items: MuscleWeek[]): { rows: WeekRow[]; muscles: string[] } {
  const muscles = [...new Set(items.map((i) => i.muscle))].sort();
  const byWeek = new Map<string, WeekRow>();
  for (const item of items) {
    const row = byWeek.get(item.week_start) ?? { week: item.week_start, total: 0 };
    row[item.muscle] = item.volume_kg;
    row.total += item.volume_kg;
    byWeek.set(item.week_start, row);
  }
  return { rows: [...byWeek.values()].sort((a, b) => a.week.localeCompare(b.week)), muscles };
}

/** Weekly kg per primary muscle, stacked. */
export function WeeklyMuscleChart({ items }: { items: MuscleWeek[] }) {
  const { rows, muscles } = pivotWeeks(items);
  const data = rows.map((r) => ({ ...r, label: formatDay(r.week) }));
  return (
    <div>
      <div style={{ height: PROGRESS_CHART_HEIGHT }} role="figure" aria-label={`Weekly volume per muscle, ${rows.length} weeks`} data-testid="muscle-chart">
        <ResponsiveContainer width="100%" height={PROGRESS_CHART_HEIGHT} initialDimension={{ width: 600, height: PROGRESS_CHART_HEIGHT }}>
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -4 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis dataKey="label" {...AXIS} />
            <YAxis {...AXIS} width={52} />
            <Tooltip formatter={(v) => (typeof v === "number" ? formatVolume(v) : String(v))} />
            <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v: string) => label(v)} />
            {muscles.map((m) => (
              <Bar key={m} dataKey={m} name={m} stackId="kg" fill={MUSCLE_COLORS[m] ?? "var(--muted)"} isAnimationActive={false} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <Details summary="Show weekly data">
        <table className="w-full text-left text-xs tabular-nums" data-testid="muscle-table">
          <caption className="sr-only">Working sets and kg per week and muscle</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1.5 pr-3 font-medium">Week of</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">Muscle</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">Sets</th>
              <th scope="col" className="py-1.5 text-right font-medium">Volume</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.map((i) => (
              <tr key={`${i.week_start}-${i.muscle}`} data-week={i.week_start} data-muscle={i.muscle} data-sets={i.sets} data-volume={i.volume_kg}>
                <th scope="row" className="py-1.5 pr-3 font-normal">{formatDay(i.week_start, true)}</th>
                <td className="py-1.5 pr-3">{label(i.muscle)}</td>
                <td className="py-1.5 pr-3 text-right">{i.sets}</td>
                <td className="py-1.5 text-right">{formatVolume(i.volume_kg)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Details>
    </div>
  );
}

/** Body weight over time. */
export function BodyWeightChart({ items }: { items: BodyMetric[] }) {
  const data = items.map((m) => ({ label: formatDay(m.date), kg: m.weight_kg }));
  return (
    <div>
      <div style={{ height: 180 }} role="figure" aria-label={`Body weight, ${items.length} entries`} data-testid="weight-chart">
        <ResponsiveContainer width="100%" height={180} initialDimension={{ width: 600, height: 180 }}>
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis dataKey="label" {...AXIS} minTickGap={16} />
            <YAxis {...AXIS} width={44} domain={["dataMin - 1", "dataMax + 1"]} />
            <Tooltip formatter={(v) => (typeof v === "number" ? formatKg(v, 1) : String(v))} />
            <Line type="monotone" dataKey="kg" name="kg" stroke="var(--chart-1)" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <Details summary="Show entries">
        <table className="w-full text-left text-xs tabular-nums" data-testid="weight-table">
          <caption className="sr-only">Body weight entries</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1.5 pr-3 font-medium">Date</th>
              <th scope="col" className="py-1.5 text-right font-medium">Weight</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.map((m) => (
              <tr key={m.date} data-date={m.date} data-weight={m.weight_kg}>
                <th scope="row" className="py-1.5 pr-3 font-normal">{formatDay(m.date, true)}</th>
                <td className="py-1.5 text-right">{formatKg(m.weight_kg, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Details>
    </div>
  );
}
