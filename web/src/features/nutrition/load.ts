import "server-only";

import { nutritionApi } from "@/features/nutrition/api";
import type { DayLog, DaySummary, Food, FoodList, Meal, Profile, RangeSummary } from "@/features/nutrition/types";
import { addDays, weekStart } from "@/features/nutrition/types";
import { type Loaded, load } from "@/lib/api";

/** Recent foods come from the logs of the last few days. */
const RECENT_DAYS = 3;
const RECENT_FOODS = 10;
const PER_100 = 100;
const ONE_DECIMAL = 10;

/** The meal a new entry most likely belongs to, by the local hour. */
const MEAL_HOURS: readonly [number, Meal][] = [
  [11, "breakfast"],
  [16, "lunch"],
  [21, "dinner"],
];

export function mealAt(hour: number): Meal {
  return MEAL_HOURS.find(([until]) => hour < until)?.[1] ?? "snack";
}

export interface FoodDay {
  date: string;
  today: string;
  summary: Loaded<DaySummary>;
  log: Loaded<DayLog>;
  weekly: Loaded<RangeSummary>;
  favorites: Food[];
  recent: Food[];
  profile: Profile | null;
  defaultMeal: Meal;
}

const per100 = (value: number | null, grams: number) =>
  value === null || grams <= 0 ? null : Math.round((value / grams) * PER_100 * ONE_DECIMAL) / ONE_DECIMAL;

/** Distinct foods of some day logs, newest first, as foods to pick again. */
export function recentFoods(logs: DayLog[]): Food[] {
  const recent = new Map<number, Food>();
  for (const day of logs) {
    for (const e of [...day.entries].reverse()) {
      if (recent.has(e.food_id)) continue;
      recent.set(e.food_id, {
        id: e.food_id,
        name: e.food_name,
        brand: e.brand,
        barcode: null,
        kcal_100g: per100(e.kcal, e.grams) ?? 0,
        protein_100g: per100(e.protein_g, e.grams),
        carbs_100g: per100(e.carbs_g, e.grams),
        fat_100g: per100(e.fat_g, e.grams),
        source: "manual",
        favorite: false,
      });
    }
  }
  return [...recent.values()].slice(0, RECENT_FOODS);
}

/** Every read of the Food page in parallel; each block fails on its own. */
export async function loadFoodDay(date: string, today: string, hour: number): Promise<FoodDay> {
  const monday = weekStart(date);
  const [summary, log, weekly, favorites, profile, ...previous] = await Promise.all([
    load(() => nutritionApi.summary(date)),
    load(() => nutritionApi.log(date)),
    load(() => nutritionApi.weekly(monday, addDays(monday, 6))),
    load<FoodList>(() => nutritionApi.favorites()),
    load(() => nutritionApi.profile()),
    ...Array.from({ length: RECENT_DAYS }, (_, i) => load(() => nutritionApi.log(addDays(date, -i)))),
  ]);
  return {
    date,
    today,
    summary,
    log,
    weekly,
    favorites: favorites.ok ? favorites.data.items : [],
    recent: recentFoods(previous.flatMap((day) => (day.ok ? [day.data] : []))),
    profile: profile.ok ? profile.data : null,
    defaultMeal: mealAt(hour),
  };
}
