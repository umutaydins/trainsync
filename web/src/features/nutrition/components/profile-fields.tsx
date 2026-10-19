"use client";

import { useTranslations } from "next-intl";
import type { ChangeEvent } from "react";

import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { BASELINES, LIMITS, type ProfileField, type ProfileValues } from "@/features/nutrition/profile";

/**
 * The nutrition profile's fields (sex, birth year, height, everyday activity, targets), used by
 * the Food page and the onboarding step alike. Controlled: the caller owns values and errors.
 */
export function ProfileFields({
  values,
  invalid,
  onChange,
}: {
  values: ProfileValues;
  invalid: ProfileField | null;
  onChange: (values: ProfileValues) => void;
}) {
  const t = useTranslations("nutrition.profile");
  const set = (key: keyof ProfileValues) => (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    onChange({ ...values, [key]: event.target.value });
  const error = (key: ProfileField) => (invalid === key ? t(`errors.${key}`, LIMITS[key]) : undefined);
  return (
    <>
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
    </>
  );
}
