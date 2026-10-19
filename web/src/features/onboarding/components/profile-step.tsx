"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { ProfileFields } from "@/features/nutrition/components/profile-fields";
import { type ProfileField, profileValues, toProfile } from "@/features/nutrition/profile";
import type { Profile } from "@/features/nutrition/types";
import { SaveButton, StepFrame, type StepProps, useSave } from "@/features/onboarding/components/step-frame";
import { put } from "@/lib/mutate";

/** Nutrition profile for the basal-rate estimate → `PUT /v1/nutrition/profile` (the Food page's fields). */
export function ProfileStep({ onNext, profile }: StepProps & { profile: Profile | null }) {
  const t = useTranslations("onboarding.profile");
  const [values, setValues] = useState(() => profileValues(profile));
  const [invalid, setInvalid] = useState<ProfileField | null>(null);
  const { busy, failed, run } = useSave(onNext);

  const save = () => {
    const checked = toProfile(values);
    if (!checked.ok) return setInvalid(checked.field);
    setInvalid(null);
    void run(async () => (await put("/v1/nutrition/profile", checked.body)).ok);
  };

  return (
    <StepFrame title={t("title")} body={t("body")} error={failed} action={<SaveButton busy={busy} onClick={save} />}>
      <ProfileFields values={values} invalid={invalid} onChange={setValues} />
    </StepFrame>
  );
}
