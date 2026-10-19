"use client";

import { useTranslations } from "next-intl";
import { useState, type ChangeEvent } from "react";

import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { SaveButton, StepFrame, type StepProps, useSave } from "@/features/onboarding/components/step-frame";
import type { ActivityBaseline, Profile, ProfileIn } from "@/features/nutrition/types";
import { put } from "@/lib/mutate";

/** The API's bounds (ProfileIn). */
export const LIMITS = {
  birthYear: { min: 1900, max: 2100 },
  height: { min: 100, max: 250 },
  kcalTarget: { min: 1, max: 10000 },
  proteinTarget: { min: 0, max: 1000 },
} as const;
const BASELINES: readonly ActivityBaseline[] = ["sedentary", "light", "moderate"];

type Values = { sex: ProfileIn["sex"]; birthYear: string; height: string; baseline: ActivityBaseline; kcalTarget: string; proteinTarget: string };
type ErrorKey = keyof typeof LIMITS;

function inRange(value: number, key: ErrorKey): boolean {
  return Number.isFinite(value) && value >= LIMITS[key].min && value <= LIMITS[key].max;
}

/** Optional whole number: null when empty, NaN when not a whole number. */
function optionalInt(text: string): number | null {
  if (text.trim() === "") return null;
  const n = Number(text);
  return Number.isInteger(n) ? n : Number.NaN;
}

/** The form's values as a `ProfileIn`, or the first field that is out of range. */
export function toProfile(values: Values): { ok: true; body: ProfileIn } | { ok: false; field: ErrorKey } {
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

/** Nutrition profile for the basal-rate estimate → `PUT /v1/nutrition/profile`. */
export function ProfileStep({ onNext, profile }: StepProps & { profile: Profile | null }) {
  const t = useTranslations("onboarding.profile");
  const [values, setValues] = useState<Values>({
    sex: profile?.sex ?? "male",
    birthYear: profile ? String(profile.birth_year) : "",
    height: profile ? String(profile.height_cm) : "",
    baseline: profile?.activity_baseline ?? "light",
    kcalTarget: profile?.kcal_target != null ? String(profile.kcal_target) : "",
    proteinTarget: profile?.protein_target_g != null ? String(profile.protein_target_g) : "",
  });
  const [invalid, setInvalid] = useState<ErrorKey | null>(null);
  const { busy, failed, run } = useSave(onNext);
  const set = (key: keyof Values) => (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setValues((v) => ({ ...v, [key]: event.target.value }));
  const error = (key: ErrorKey) => (invalid === key ? t(`errors.${key}`, LIMITS[key]) : undefined);

  const save = () => {
    const checked = toProfile(values);
    if (!checked.ok) return setInvalid(checked.field);
    setInvalid(null);
    void run(async () => (await put("/v1/nutrition/profile", checked.body)).ok);
  };

  return (
    <StepFrame title={t("title")} body={t("body")} error={failed} action={<SaveButton busy={busy} onClick={save} />}>
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label={t("sex")}>
          <Select value={values.sex} onChange={set("sex")}>
            <option value="male">{t("male")}</option>
            <option value="female">{t("female")}</option>
          </Select>
        </Field>
        <Field label={t("birthYear")} error={error("birthYear")}>
          <Input inputMode="numeric" autoComplete="bday-year" value={values.birthYear} onChange={set("birthYear")} />
        </Field>
        <Field label={t("height")} error={error("height")}>
          <Input inputMode="decimal" value={values.height} onChange={set("height")} />
        </Field>
      </div>
      <Field label={t("baseline")}>
        <Select value={values.baseline} onChange={set("baseline")}>
          {BASELINES.map((baseline) => (
            <option key={baseline} value={baseline}>
              {t(`baselines.${baseline}`)}
            </option>
          ))}
        </Select>
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("kcalTarget")} error={error("kcalTarget")}>
          <Input inputMode="numeric" value={values.kcalTarget} onChange={set("kcalTarget")} />
        </Field>
        <Field label={t("proteinTarget")} error={error("proteinTarget")}>
          <Input inputMode="numeric" value={values.proteinTarget} onChange={set("proteinTarget")} />
        </Field>
      </div>
    </StepFrame>
  );
}
