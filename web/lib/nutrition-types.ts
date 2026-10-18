import type { components } from "@/lib/api-types";

type Schemas = components["schemas"];

export type Food = Schemas["FoodOut"];
export type FoodIn = Schemas["FoodIn"];
export type FoodList = Schemas["FoodList"];
export type FoodLookup = Schemas["FoodLookup"];
export type LogEntry = Schemas["LogOut"];
export type LogIn = Schemas["LogIn"];
export type DayLog = Schemas["DayLog"];
export type DaySummary = Schemas["DaySummary"];
export type RangeSummary = Schemas["RangeSummary"];
export type Profile = Schemas["ProfileOut"];
export type ProfileIn = Schemas["ProfileIn"];
export type Meal = Schemas["Meal"];
export type ActivityBaseline = Schemas["ActivityBaseline"];
export type EstimateGap = Schemas["EstimateGap"];

export const MEALS: readonly Meal[] = ["breakfast", "lunch", "dinner", "snack"];

const NUMBER = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const ONE = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

export function kcal(value: number): string {
  return `${NUMBER.format(value)} kcal`;
}

export function grams(value: number): string {
  return `${ONE.format(value)} g`;
}

/** Per-100 g values scaled to `g` grams; null stays null (unknown). */
export function scaled(per100: number | null, g: number): number | null {
  return per100 === null ? null : (per100 * g) / 100;
}

/** Today in UTC (`YYYY-MM-DD`): food log days are UTC days, like the rest of the API (ADR 0019). */
export function utcToday(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

export function addDays(day: string, delta: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
}

/** Monday of the ISO week of `day`. */
export function weekStart(day: string): string {
  const d = new Date(`${day}T00:00:00Z`);
  return addDays(day, -((d.getUTCDay() + 6) % 7));
}

export const ESTIMATE_GAP_TEXT: Record<EstimateGap, string> = {
  no_profile: "Add a profile (below) to estimate the basal rate.",
  no_body_weight: "Add a body weight (below) to estimate the basal rate.",
};
