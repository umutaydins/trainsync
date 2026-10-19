"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { BodyMetric, ExerciseProgress, MuscleWeek } from "@/features/training/types";
import { useTrainingFormat } from "@/features/training/use-training-format";

export const PROGRESS_CHART_HEIGHT = 240;
const WEIGHT_CHART_HEIGHT = 180;
const E1RM_DIGITS = 1;

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

function Details({ summary, children }: { summary: string; children: ReactNode }) {
  return (
    <details className="mt-3 text-sm">
      <summary className="flex min-h-touch cursor-pointer items-center text-sm font-semibold text-muted hover:text-text">{summary}</summary>
      <div className="mt-2 overflow-x-auto">{children}</div>
    </details>
  );
}

/** e1RM and best-set weight per workout for one exercise, oldest first. */
export function ExerciseProgressChart({ progress }: { progress: ExerciseProgress }) {
  const t = useTranslations("training.lifts.chart");
  const fmt = useTrainingFormat();
  const name = progress.exercise.name;
  const data = progress.sessions.map((s) => ({
    label: fmt.date(s.started_at),
    e1rm: s.e1rm_kg,
    best: s.best_set?.weight_kg ?? null,
  }));
  return (
    <div>
      <div style={{ height: PROGRESS_CHART_HEIGHT }} role="figure" aria-label={t("exerciseLabel", { name })} data-testid="exercise-chart">
        <ResponsiveContainer width="100%" height={PROGRESS_CHART_HEIGHT} initialDimension={{ width: 600, height: PROGRESS_CHART_HEIGHT }}>
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis dataKey="label" {...AXIS} minTickGap={16} />
            <YAxis {...AXIS} width={44} />
            <Tooltip formatter={(v) => (typeof v === "number" ? fmt.kg(v, E1RM_DIGITS) : String(v))} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="e1rm" name={t("e1rm")} stroke="var(--chart-1)" strokeWidth={2} dot={{ r: 3 }} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="best" name={t("best")} stroke="var(--chart-2)" strokeWidth={2} dot={{ r: 3 }} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <Details summary={t("showSessions")}>
        <table className="w-full text-left text-xs tabular-nums" data-testid="exercise-table">
          <caption className="sr-only">{t("sessionsCaption", { name })}</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1.5 pr-3 font-medium">{t("workout")}</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">{t("bestSet")}</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">{t("e1rm")}</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">{t("volume")}</th>
              <th scope="col" className="py-1.5 text-right font-medium">{t("sets")}</th>
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
                <th scope="row" className="py-1.5 pr-3 font-normal">{fmt.date(s.started_at)}</th>
                <td className="py-1.5 pr-3 text-right">{s.best_set ? t("bestValue", { reps: s.best_set.reps, weight: fmt.kg(s.best_set.weight_kg) }) : "—"}</td>
                <td className="py-1.5 pr-3 text-right">{s.e1rm_kg !== null ? fmt.kg(s.e1rm_kg, E1RM_DIGITS) : "—"}</td>
                <td className="py-1.5 pr-3 text-right">{fmt.volume(s.volume_kg)}</td>
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
  const t = useTranslations("training.lifts.chart");
  const muscleName = useTranslations("progress.strength.muscles");
  const fmt = useTrainingFormat();
  const { rows, muscles } = pivotWeeks(items);
  const data = rows.map((r) => ({ ...r, label: fmt.day(r.week) }));
  return (
    <div>
      <div style={{ height: PROGRESS_CHART_HEIGHT }} role="figure" aria-label={t("muscleLabel", { count: rows.length })} data-testid="muscle-chart">
        <ResponsiveContainer width="100%" height={PROGRESS_CHART_HEIGHT} initialDimension={{ width: 600, height: PROGRESS_CHART_HEIGHT }}>
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -4 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis dataKey="label" {...AXIS} />
            <YAxis {...AXIS} width={52} />
            <Tooltip formatter={(v) => (typeof v === "number" ? fmt.volume(v) : String(v))} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {muscles.map((m) => (
              <Bar key={m} dataKey={m} name={muscleName(m)} stackId="kg" fill={MUSCLE_COLORS[m] ?? "var(--muted)"} isAnimationActive={false} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <Details summary={t("showWeeks")}>
        <table className="w-full text-left text-xs tabular-nums" data-testid="muscle-table">
          <caption className="sr-only">{t("weeksCaption")}</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1.5 pr-3 font-medium">{t("weekOf")}</th>
              <th scope="col" className="py-1.5 pr-3 font-medium">{t("muscle")}</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">{t("sets")}</th>
              <th scope="col" className="py-1.5 text-right font-medium">{t("volume")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.map((i) => (
              <tr key={`${i.week_start}-${i.muscle}`} data-week={i.week_start} data-muscle={i.muscle} data-sets={i.sets} data-volume={i.volume_kg}>
                <th scope="row" className="py-1.5 pr-3 font-normal">{fmt.day(i.week_start, true)}</th>
                <td className="py-1.5 pr-3">{muscleName(i.muscle)}</td>
                <td className="py-1.5 pr-3 text-right">{i.sets}</td>
                <td className="py-1.5 text-right">{fmt.volume(i.volume_kg)}</td>
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
  const t = useTranslations("training.lifts.chart");
  const fmt = useTrainingFormat();
  const data = items.map((m) => ({ label: fmt.day(m.date), kg: m.weight_kg }));
  return (
    <div>
      <div style={{ height: WEIGHT_CHART_HEIGHT }} role="figure" aria-label={t("weightLabel", { count: items.length })} data-testid="weight-chart">
        <ResponsiveContainer width="100%" height={WEIGHT_CHART_HEIGHT} initialDimension={{ width: 600, height: WEIGHT_CHART_HEIGHT }}>
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis dataKey="label" {...AXIS} minTickGap={16} />
            <YAxis {...AXIS} width={44} domain={["dataMin - 1", "dataMax + 1"]} />
            <Tooltip formatter={(v) => (typeof v === "number" ? fmt.kg(v, E1RM_DIGITS) : String(v))} />
            <Line type="monotone" dataKey="kg" name={t("weightColumn")} stroke="var(--chart-1)" strokeWidth={2} dot={{ r: 2 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <Details summary={t("showEntries")}>
        <table className="w-full text-left text-xs tabular-nums" data-testid="weight-table">
          <caption className="sr-only">{t("entriesCaption")}</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1.5 pr-3 font-medium">{t("date")}</th>
              <th scope="col" className="py-1.5 text-right font-medium">{t("weightColumn")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.map((m) => (
              <tr key={m.date} data-date={m.date} data-weight={m.weight_kg}>
                <th scope="row" className="py-1.5 pr-3 font-normal">{fmt.day(m.date, true)}</th>
                <td className="py-1.5 text-right">{fmt.kg(m.weight_kg)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Details>
    </div>
  );
}
