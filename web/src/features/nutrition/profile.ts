/**
 * The nutrition profile form's values and checks, shared by Food and the onboarding (one form,
 * one set of rules: the API's bounds of `ProfileIn`). Pure, so it is tested without React.
 */

import type { ActivityBaseline, Profile, ProfileIn } from "@/features/nutrition/types";

export const LIMITS = {
  birthYear: { min: 1900, max: 2100 },
  height: { min: 100, max: 250 },
  kcalTarget: { min: 1, max: 10000 },
  proteinTarget: { min: 0, max: 1000 },
} as const;

export const BASELINES: readonly ActivityBaseline[] = ["sedentary", "light", "moderate"];

export type ProfileValues = {
  sex: ProfileIn["sex"];
  birthYear: string;
  height: string;
  baseline: ActivityBaseline;
  kcalTarget: string;
  proteinTarget: string;
};
export type ProfileField = keyof typeof LIMITS;

export function profileValues(profile: Profile | null): ProfileValues {
  return {
    sex: profile?.sex ?? "male",
    birthYear: profile ? String(profile.birth_year) : "",
    height: profile ? String(profile.height_cm) : "",
    baseline: profile?.activity_baseline ?? "light",
    kcalTarget: profile?.kcal_target != null ? String(profile.kcal_target) : "",
    proteinTarget: profile?.protein_target_g != null ? String(profile.protein_target_g) : "",
  };
}

function inRange(value: number, key: ProfileField): boolean {
  return Number.isFinite(value) && value >= LIMITS[key].min && value <= LIMITS[key].max;
}

/** Optional whole number: null when empty, NaN when not a whole number. */
function optionalInt(text: string): number | null {
  if (text.trim() === "") return null;
  const n = Number(text);
  return Number.isInteger(n) ? n : Number.NaN;
}

/** The form's values as a `ProfileIn`, or the first field that is out of range. */
export function toProfile(values: ProfileValues): { ok: true; body: ProfileIn } | { ok: false; field: ProfileField } {
  const birthYear = Number(values.birthYear);
  const height = Number(values.height.replace(",", "."));
  const kcal = optionalInt(values.kcalTarget);
  const protein = optionalInt(values.proteinTarget);
  if (!Number.isInteger(birthYear) || !inRange(birthYear, "birthYear")) return { ok: false, field: "birthYear" };
  if (!inRange(height, "height")) return { ok: false, field: "height" };
  if (kcal !== null && !inRange(kcal, "kcalTarget")) return { ok: false, field: "kcalTarget" };
  if (protein !== null && !inRange(protein, "proteinTarget")) return { ok: false, field: "proteinTarget" };
  return {
    ok: true,
    body: {
      sex: values.sex,
      birth_year: birthYear,
      height_cm: height,
      activity_baseline: values.baseline,
      kcal_target: kcal,
      protein_target_g: protein,
    },
  };
}
