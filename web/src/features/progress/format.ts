import type { Change, SportGroup } from "@/features/progress/types";
import { PACE_GROUPS } from "@/features/progress/types";

/** Pure, locale-aware number and date helpers of the progress and Today screens. */

const SECONDS_PER_MINUTE = 60;
const METERS_PER_KM = 1000;
const SWIM_PACE_METERS = 100;
const MPS_TO_KMH = 3.6;
const PERCENT = 100;

export function formatNumber(locale: string, value: number, digits = 0): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: digits, minimumFractionDigits: 0 }).format(value);
}

/** Axis ticks at 375 px: `12K`, `1,5 B` (Turkish), never more than three characters of digits. */
export function formatCompact(locale: string, value: number): string {
  return new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

/** A share 0..1 as a whole percent. */
export function formatShare(locale: string, share: number): string {
  return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 0 }).format(share);
}

/** The size of a change in percent (`12%`), without its sign: the badge's arrow carries it. */
export function formatChangePct(locale: string, pct: number): string {
  return formatShare(locale, Math.abs(pct) / PERCENT);
}

export function km(meters: number): number {
  return meters / METERS_PER_KM;
}

function clock(seconds: number): string {
  const total = Math.round(seconds);
  return `${Math.floor(total / SECONDS_PER_MINUTE)}:${String(total % SECONDS_PER_MINUTE).padStart(2, "0")}`;
}

export type EffortUnit = "perKm" | "per100m" | "kmh";

export function effortUnit(group: SportGroup): EffortUnit {
  if (!PACE_GROUPS.has(group)) return "kmh";
  return group === "swim" ? "per100m" : "perKm";
}

/** A sport group's effort from its average speed: pace (`5:20`) or speed (`28.4`). */
export function formatEffort(locale: string, group: SportGroup, speedMps: number | null): string | null {
  if (speedMps == null || !(speedMps > 0)) return null;
  const unit = effortUnit(group);
  if (unit === "kmh") return formatNumber(locale, speedMps * MPS_TO_KMH, 1);
  const meters = unit === "per100m" ? SWIM_PACE_METERS : METERS_PER_KM;
  return clock(meters / speedMps);
}

/**
 * The change of a pace in percent, from the change of the speed it comes from (a pace is the
 * inverse of a speed: 10% faster is about 9% less time per km).
 */
export function paceChangePct(speed: Change): number | null {
  if (speed.value == null || speed.previous == null || !(speed.value > 0) || !(speed.previous > 0)) return null;
  return (speed.previous / speed.value - 1) * PERCENT;
}

/** A calendar day (`YYYY-MM-DD`, no zone) in the user's language. */
export function formatDay(locale: string, day: string, options: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" }): string {
  return new Intl.DateTimeFormat(locale, { ...options, timeZone: "UTC" }).format(new Date(`${day}T00:00:00Z`));
}

/** `from – to` of a window, the year once when both share it. */
export function formatWindow(locale: string, from: string, to: string): string {
  const format = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  return format.formatRange(new Date(`${from}T00:00:00Z`), new Date(`${to}T00:00:00Z`));
}

/** The local calendar day of `now` in `timeZone`. */
export function localDay(now: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** The local hour (0–23) of `now` in `timeZone`. */
export function localHour(now: Date, timeZone: string): number {
  const hour = new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", hourCycle: "h23" }).format(now);
  return Number(hour);
}

/** A bucket's start on an axis: `12 Oct` for days and weeks, `Oct 26` for months. */
export function formatBucket(locale: string, start: string, bucket: "day" | "week" | "month"): string {
  return bucket === "month"
    ? formatDay(locale, start, { month: "short", year: "2-digit" })
    : formatDay(locale, start);
}
