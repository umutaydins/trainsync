import type { Better } from "@/components/ui/change";
import type { components } from "@/lib/api-types";

type Schemas = components["schemas"];

/** The full `/v1/stats/summary` (lib/types keeps a narrowed one for the activity pages). */
export type ProgressSummary = Schemas["StatsSummary"];
export type Change = Schemas["Change"];
export type Period = Schemas["Period"];
export type Metric = Schemas["Metric"];
export type Bucket = Schemas["Bucket"];
export type SportGroup = Schemas["SportGroup"];
export type SportGroupStats = Schemas["SportGroupOut"];
export type Endurance = Schemas["EnduranceOut"];
export type Strength = Schemas["StrengthOut"];
export type Adherence = Schemas["AdherenceOut"];
export type ExerciseStats = Schemas["ExerciseProgressOut"];
export type MuscleStats = Schemas["MuscleProgressOut"];
export type Consistency = Schemas["ConsistencyOut"];
export type NutritionStats = Schemas["NutritionOut"];
export type BodyStats = Schemas["BodyOut"];
export type StatsWindow = Schemas["WindowOut"];
export type Series = Schemas["SeriesOut"];
export type SeriesPoint = Schemas["PointOut"];
export type Heatmap = Schemas["HeatmapOut"];
export type HeatmapDay = Schemas["HeatmapDayOut"];
export type Records = Schemas["PrsOut"];
export type PersonalRecord = Schemas["PrOut"];
export type CheckinStatus = Schemas["CheckinStatus"];

/** The switcher's tabs, shortest first; `custom` opens the date range sheet. */
export const PERIOD_TABS = ["week", "month", "3m", "6m", "year", "all"] as const satisfies readonly Period[];
const PERIODS: readonly Period[] = [
  "week",
  "last_week",
  "month",
  "last_month",
  "3m",
  "6m",
  "year",
  "12m",
  "all",
  "custom",
];
export const DEFAULT_PERIOD: Period = "month";

/** What `/progress?period=…&from=…&to=…` asks for (`from`/`to` only with `custom`). */
export interface PeriodQuery {
  period: Period;
  from?: string;
  to?: string;
  /** The lift of the e1RM chart (`?lift=<exercise id>`). */
  lift?: number;
  /** The heatmap's year (`?year=`). */
  year?: number;
}

type SearchParams = Record<string, string | string[] | undefined>;

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const ID_RE = /^\d{1,9}$/;
const YEAR_RE = /^\d{4}$/;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function isDay(value: string | undefined): value is string {
  return !!value && DATE_RE.test(value) && new Date(`${value}T00:00:00Z`).toISOString().startsWith(value);
}

export type RangeError = "missing" | "order";

/** Why a custom range cannot be shown, or null when it can. */
export function rangeError(from: string | undefined, to: string | undefined): RangeError | null {
  if (!isDay(from) || !isDay(to)) return "missing";
  return from <= to ? null : "order";
}

function isPeriod(value: string | undefined): value is Period {
  return !!value && (PERIODS as readonly string[]).includes(value);
}

/** The URL's period; an invalid one (or a broken custom range) falls back to the default. */
export function parsePeriod(params: SearchParams): PeriodQuery {
  const raw = first(params.period);
  const from = first(params.from);
  const to = first(params.to);
  const liftRaw = first(params.lift);
  const yearRaw = first(params.year);
  const extra = {
    lift: liftRaw && ID_RE.test(liftRaw) ? Number(liftRaw) : undefined,
    year: yearRaw && YEAR_RE.test(yearRaw) ? Number(yearRaw) : undefined,
  };
  if (raw === "custom") {
    return rangeError(from, to) === null ? { period: "custom", from, to, ...extra } : { period: DEFAULT_PERIOD, ...extra };
  }
  return { period: isPeriod(raw) ? raw : DEFAULT_PERIOD, ...extra };
}

/** The shareable URL of a period (and the other choices of the page). */
export function progressHref(query: PeriodQuery): string {
  const search = new URLSearchParams({ period: query.period });
  if (query.period === "custom" && query.from && query.to) {
    search.set("from", query.from);
    search.set("to", query.to);
  }
  if (query.lift !== undefined) search.set("lift", String(query.lift));
  if (query.year !== undefined) search.set("year", String(query.year));
  return `/progress?${search.toString()}`;
}

/** Up to this many days a day bucket fits a phone-wide chart (ADR 0038: day, week, month). */
const DAY_BUCKET_MAX_DAYS = 31;
const WEEK_BUCKET_MAX_DAYS = 183;
const DAY_MS = 86_400_000;

/** The bucket the API picks by default, for a window of `days`. */
export function defaultBucket(days: number): Bucket {
  if (days <= DAY_BUCKET_MAX_DAYS) return "day";
  return days <= WEEK_BUCKET_MAX_DAYS ? "week" : "month";
}

export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS) + 1;
}

/** Which direction is good news per stat (body and food are neutral by design, P6.7). */
export const BETTER = {
  distance: "up",
  time: "up",
  elevation: "up",
  count: "up",
  pace: "down",
  speed: "up",
  heartrate: "neither",
  sessions: "up",
  sets: "up",
  reps: "up",
  tonnage: "up",
  prs: "up",
  activeDays: "up",
  checkinRate: "up",
  loggingRate: "up",
  nutrition: "neither",
  weight: "neither",
} as const satisfies Record<string, Better>;

/** The groups whose effort reads as a pace (min/km, min/100 m); the rest as a speed. */
export const PACE_GROUPS: ReadonlySet<SportGroup> = new Set(["run", "walk", "swim"]);

/** No previous period (`all`), or a previous value of 0: no change to show. */
export function hasChange(change: Change | null | undefined, period: Period): change is Change {
  return period !== "all" && change != null && change.change_pct != null;
}
