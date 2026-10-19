import type { DaySummary, Food, LogEntry, Profile, RangeSummary } from "@/features/nutrition/types";

export function food(id: number, overrides: Partial<Food> = {}): Food {
  return {
    id,
    name: `Food ${id}`,
    brand: null,
    barcode: null,
    kcal_100g: 100,
    protein_100g: 10,
    carbs_100g: 10,
    fat_100g: 1,
    source: "manual",
    favorite: false,
    ...overrides,
  };
}

export const OATS = food(7, { name: "Rolled oats", brand: "Acme", kcal_100g: 372, protein_100g: 13.5, carbs_100g: 58.7, fat_100g: 7, favorite: true });
export const CHICKEN = food(8, { name: "Chicken breast, cooked", kcal_100g: 165, protein_100g: 31, carbs_100g: 0, fat_100g: 3.6 });

export function entry(overrides: Partial<LogEntry> = {}): LogEntry {
  return {
    client_id: "0b6f1f9e-4c1e-4a8e-9a43-2f1d8f0c6a11",
    date: "2026-10-18",
    meal: "breakfast",
    food_id: 7,
    food_name: "Rolled oats",
    brand: "Acme",
    grams: 80,
    kcal: 297.6,
    protein_g: 10.8,
    carbs_g: 47,
    fat_g: 5.6,
    created_at: "2026-10-18T07:00:00Z",
    ...overrides,
  };
}

export function daySummary(overrides: Partial<DaySummary> = {}): DaySummary {
  return {
    date: "2026-10-18",
    intake_kcal: 1890.4,
    protein_g: 132.5,
    carbs_g: 201.2,
    fat_g: 61.3,
    sugars_g: 0,
    free_sugars_g: 0,
    entry_count: 6,
    macros_complete: true,
    kcal_target: 2400,
    protein_target_g: 140,
    kcal_remaining: 509.6,
    bmr_kcal: 1755.5,
    baseline_kcal: 2413.8,
    activity_baseline: "light",
    weight_kg: 78.4,
    weight_date: "2026-10-17",
    estimate_unavailable_reason: null,
    exercise_kcal: 612,
    exercise_unknown_count: 0,
    exercise_complete: true,
    activities: [
      { strava_activity_id: 1, name: "Morning run", sport_type: "Run", start_date: "2026-10-18T06:00:00Z", kcal: 612, kcal_known: true, kcal_source: "calories" },
    ],
    expenditure_kcal: 3025.8,
    balance_kcal: -1135.4,
    balance_complete: true,
    ...overrides,
  };
}

export const UNKNOWN_EXERCISE: Partial<DaySummary> = {
  exercise_unknown_count: 1,
  exercise_complete: false,
  activities: [
    { strava_activity_id: 1, name: "Morning run", sport_type: "Run", start_date: "2026-10-18T06:00:00Z", kcal: 612, kcal_known: true, kcal_source: "calories" },
    { strava_activity_id: 2, name: "Gym", sport_type: "WeightTraining", start_date: "2026-10-18T17:00:00Z", kcal: null, kcal_known: false, kcal_source: null },
  ],
  balance_complete: false,
};

export const NO_PROFILE: Partial<DaySummary> = {
  kcal_target: null,
  protein_target_g: null,
  kcal_remaining: null,
  bmr_kcal: null,
  baseline_kcal: null,
  activity_baseline: null,
  weight_kg: null,
  weight_date: null,
  estimate_unavailable_reason: "no_profile",
  expenditure_kcal: null,
  balance_kcal: null,
  balance_complete: false,
};

export function weekly(): RangeSummary {
  return {
    from: "2026-10-12",
    to: "2026-10-18",
    days: [
      daySummary({ date: "2026-10-12", intake_kcal: 2100, protein_g: 120, entry_count: 4 }),
      daySummary({ date: "2026-10-13", intake_kcal: 0, protein_g: 0, entry_count: 0 }),
      daySummary({ date: "2026-10-18" }),
    ],
    totals: {
      intake_kcal: 3990.4,
      exercise_kcal: 1836,
      days_logged: 2,
      avg_intake_kcal: 1995.2,
      balance_kcal: -3200,
      balance_days: 3,
      balance_complete: true,
    },
  };
}

export function profile(overrides: Partial<Profile> = {}): Profile {
  return {
    sex: "male",
    birth_year: 1990,
    height_cm: 180,
    activity_baseline: "light",
    kcal_target: 2400,
    protein_target_g: 140,
    bmr_kcal: 1755.5,
    weight_kg: 78.4,
    weight_date: "2026-10-17",
    estimate_unavailable_reason: null,
    warning: null,
    updated_at: "2026-10-18T07:00:00Z",
    ...overrides,
  };
}
