import type { components } from "@/lib/api-types";

/** Daily check-ins (P6.9, ADR 0020): types and pure helpers shared by server and client code. */

type Schemas = components["schemas"];

export type Checkin = Schemas["CheckinOut"];
export type CheckinIn = Schemas["CheckinIn"];
export type CheckinStatus = Schemas["CheckinStatus"];
export type CheckinSummary = Schemas["CheckinSummary"];
export type CheckinList = Schemas["CheckinList"];

export const STATUSES: readonly CheckinStatus[] = ["done", "partial", "skipped", "rest", "sick_or_injured"];

/** A glyph per status besides its colour (colour is never the only cue); the label is `checkins.statuses.<status>`. */
export const STATUS_META: Record<CheckinStatus, { glyph: string; cell: string }> = {
  done: { glyph: "✓", cell: "bg-ok text-white" },
  partial: { glyph: "½", cell: "bg-ok-soft text-ok ring-1 ring-inset ring-ok/40" },
  skipped: { glyph: "✕", cell: "bg-bad-soft text-bad ring-1 ring-inset ring-bad/40" },
  rest: { glyph: "z", cell: "bg-accent-soft text-accent-ink" },
  sick_or_injured: { glyph: "+", cell: "bg-warn-soft text-warn ring-1 ring-inset ring-warn/40" },
};

const DAY_MS = 86_400_000;
const PERCENT = 100;
/** Any Monday, to name the weekdays in the user's language. */
const MONDAY = Date.UTC(2024, 0, 1);
const WEEK_DAYS = 7;

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

/** `Mon, Oct 5` / `5 Eki Pzt`: a check-in day in the user's language. */
export function dayLabel(locale: string, day: string): string {
  return new Intl.DateTimeFormat(locale, { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(parseDay(day));
}

/** One-letter weekday names, Monday first. */
export function weekdayInitials(locale: string): string[] {
  const format = new Intl.DateTimeFormat(locale, { weekday: "narrow", timeZone: "UTC" });
  return Array.from({ length: WEEK_DAYS }, (_, i) => format.format(MONDAY + i * DAY_MS));
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

export function formatAdherence(locale: string, summary: Pick<CheckinSummary, "adherence">): string {
  if (summary.adherence === null) return "—";
  return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 0 }).format(Math.round(summary.adherence * PERCENT) / PERCENT);
}
