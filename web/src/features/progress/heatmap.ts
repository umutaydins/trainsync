import type { HeatmapDay } from "@/features/progress/types";

/** Pure layout of the year heatmap: weeks as columns (Monday first), weekdays as rows. */

const DAYS_PER_WEEK = 7;
/** Intensity steps above "nothing": 1..LEVELS of the accent. */
export const LEVELS = 4;

export interface HeatmapGrid {
  /** `rows[weekday][week]`: the day, or null before 1 January and after 31 December. */
  rows: (HeatmapDay | null)[][];
  weeks: number;
  /** Each month's first week column (for the month labels). */
  months: { month: number; week: number }[];
}

function weekdayOf(day: string): number {
  return (new Date(`${day}T00:00:00Z`).getUTCDay() + DAYS_PER_WEEK - 1) % DAYS_PER_WEEK;
}

export function heatmapGrid(days: readonly HeatmapDay[]): HeatmapGrid {
  const sorted = [...days].sort((a, b) => a.day.localeCompare(b.day));
  const offset = sorted[0] ? weekdayOf(sorted[0].day) : 0;
  const weeks = Math.ceil((sorted.length + offset) / DAYS_PER_WEEK);
  const rows: (HeatmapDay | null)[][] = Array.from({ length: DAYS_PER_WEEK }, () => Array<HeatmapDay | null>(weeks).fill(null));
  const months: HeatmapGrid["months"] = [];
  sorted.forEach((day, index) => {
    const slot = index + offset;
    const week = Math.floor(slot / DAYS_PER_WEEK);
    const row = rows[slot % DAYS_PER_WEEK];
    if (row) row[week] = day;
    if (day.day.endsWith("-01")) months.push({ month: Number(day.day.slice(5, 7)), week });
  });
  return { rows, weeks, months };
}

/** 0 for a day without training, else 1..LEVELS by its share of the year's busiest day. */
export function level(value: number, max: number): number {
  if (!(value > 0) || !(max > 0)) return 0;
  return Math.min(LEVELS, Math.max(1, Math.ceil((value / max) * LEVELS)));
}

/** Where the arrow keys move from `index` (a day of the year, 0-based) within `count` days. */
export function moveFocus(index: number, key: string, count: number): number | null {
  const step: Record<string, number> = { ArrowLeft: -DAYS_PER_WEEK, ArrowRight: DAYS_PER_WEEK, ArrowUp: -1, ArrowDown: 1 };
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  const delta = step[key];
  if (delta === undefined) return null;
  return Math.min(count - 1, Math.max(0, index + delta));
}
