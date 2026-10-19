/** Dashboard date ranges. All dates are UTC calendar days (`YYYY-MM-DD`), like the stats API. */

export const PRESETS = [
  { id: "4w", label: "4 weeks", weeks: 4 },
  { id: "12w", label: "12 weeks", weeks: 12 },
  { id: "52w", label: "52 weeks", weeks: 52 },
] as const;

export type PresetId = (typeof PRESETS)[number]["id"];
export const DEFAULT_PRESET: PresetId = "12w";

export interface DashboardRange {
  preset: PresetId | "custom";
  from: string;
  to: string;
  sportType?: string;
}

type SearchParams = Record<string, string | string[] | undefined>;

const DAY_MS = 86_400_000;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function isValidDay(value: string | undefined): value is string {
  return !!value && DATE_RE.test(value) && isoDay(new Date(`${value}T00:00:00Z`)) === value;
}

/** Monday of the ISO week containing `date` (UTC). */
export function weekStart(date: Date): Date {
  const day = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const offset = (day.getUTCDay() + 6) % 7;
  return new Date(day.getTime() - offset * DAY_MS);
}

/** Last N ISO weeks including the current one: Monday N-1 weeks ago → today. */
export function presetRange(weeks: number, today: Date): { from: string; to: string } {
  const from = new Date(weekStart(today).getTime() - (weeks - 1) * 7 * DAY_MS);
  return { from: isoDay(from), to: isoDay(today) };
}

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/**
 * `?range=4w|12w|52w` picks a preset; valid `from` and `to` (with `from <= to`) make a custom range.
 * Anything else falls back to the default preset.
 */
export function parseRange(params: SearchParams, today: Date): DashboardRange {
  const sportType = first(params.sport_type) || undefined;
  const from = first(params.from);
  const to = first(params.to);
  if (isValidDay(from) && isValidDay(to) && from <= to) {
    return { preset: "custom", from, to, sportType };
  }
  const requested = first(params.range);
  const preset = PRESETS.find((p) => p.id === requested) ?? PRESETS.find((p) => p.id === DEFAULT_PRESET);
  const weeks = preset?.weeks ?? 12;
  return { preset: preset?.id ?? DEFAULT_PRESET, ...presetRange(weeks, today), sportType };
}

/** Query string for a dashboard link with the given changes. */
export function rangeHref(range: DashboardRange, change: Partial<DashboardRange>): string {
  const next = { ...range, ...change };
  const params = new URLSearchParams();
  if (next.preset === "custom") {
    params.set("from", next.from);
    params.set("to", next.to);
  } else if (next.preset !== DEFAULT_PRESET) {
    params.set("range", next.preset);
  }
  if (next.sportType) params.set("sport_type", next.sportType);
  const query = params.toString();
  return query ? `/?${query}` : "/";
}
