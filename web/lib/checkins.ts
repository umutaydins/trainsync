import type { components } from "@/lib/api-types";

/** Daily check-ins (P6.9, ADR 0020): types and pure helpers shared by server and client code. */

type Schemas = components["schemas"];

export type Checkin = Schemas["CheckinOut"];
export type CheckinIn = Schemas["CheckinIn"];
export type CheckinStatus = Schemas["CheckinStatus"];
export type CheckinSummary = Schemas["CheckinSummary"];
export type CheckinList = Schemas["CheckinList"];

export const STATUSES: readonly CheckinStatus[] = ["done", "partial", "skipped", "rest", "sick_or_injured"];

/** Label and a glyph per status: colour is never the only cue. */
export const STATUS_META: Record<CheckinStatus, { label: string; glyph: string; cell: string }> = {
  done: { label: "Done", glyph: "✓", cell: "bg-ok text-white" },
  partial: { label: "Partly", glyph: "½", cell: "bg-ok-soft text-ok ring-1 ring-inset ring-ok/40" },
  skipped: { label: "Skipped", glyph: "✕", cell: "bg-bad-soft text-bad ring-1 ring-inset ring-bad/40" },
  rest: { label: "Rest day", glyph: "z", cell: "bg-accent/15 text-accent" },
  sick_or_injured: { label: "Sick or injured", glyph: "+", cell: "bg-warn-soft text-warn ring-1 ring-inset ring-warn/40" },
};

const DAY_MS = 86_400_000;
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;

/** `YYYY-MM-DD` ↔ a UTC-midnight timestamp; check-in dates are plain local days, no time zone. */
export function parseDay(day: string): number {
  return Date.parse(`${day}T00:00:00Z`);
}

export function formatDayKey(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

/** Monday = 0 … Sunday = 6. */
export function weekdayIndex(day: string): number {
  return (new Date(parseDay(day)).getUTCDay() + 6) % 7;
}

export function dayLabel(day: string): string {
  const d = new Date(parseDay(day));
  return `${WEEKDAYS[weekdayIndex(day)]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

export interface HeatmapCell {
  day: string;
  status: CheckinStatus | null;
  inRange: boolean;
}

/** Whole ISO weeks (Monday first) covering `from`..`to`; days outside the range are padding. */
export function heatmapWeeks(from: string, to: string, items: readonly Checkin[]): HeatmapCell[][] {
  const byDay = new Map(items.map((c) => [c.date, c.status]));
  const start = parseDay(from) - weekdayIndex(from) * DAY_MS;
  const end = parseDay(to);
  const weeks: HeatmapCell[][] = [];
  for (let monday = start; monday <= end; monday += 7 * DAY_MS) {
    const week: HeatmapCell[] = [];
    for (let i = 0; i < 7; i++) {
      const day = formatDayKey(monday + i * DAY_MS);
      const inRange = day >= from && day <= to;
      week.push({ day, inRange, status: inRange ? (byDay.get(day) ?? null) : null });
    }
    weeks.push(week);
  }
  return weeks;
}

export function formatAdherence(summary: Pick<CheckinSummary, "adherence">): string {
  return summary.adherence === null ? "—" : `${Math.round(summary.adherence * 100)}%`;
}

export function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}
