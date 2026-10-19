"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Field } from "@/components/ui/field";
import { Select } from "@/components/ui/input";
import { ChoiceCards } from "@/features/onboarding/components/choice-cards";
import { SaveButton, StepFrame, type StepProps, useSave } from "@/features/onboarding/components/step-frame";
import type { Lang, MePatch, SettingsPatch } from "@/features/onboarding/types";
import { patch } from "@/lib/mutate";
import { useBrowserTimeZones } from "@/lib/time-zones";

/** Time zone: the browser's, preselected → `PATCH /v1/me` (the BFF refreshes the `tz` cookie). */
export function TimeZoneStep({ onNext, current }: StepProps & { current: string | null }) {
  const t = useTranslations("onboarding.timezone");
  const router = useRouter();
  const { zone: browserZone, zones } = useBrowserTimeZones();
  const [chosen, setChosen] = useState("");
  const zone = chosen || browserZone || current || "";
  const { busy, failed, run } = useSave(onNext);

  const save = () =>
    run(async () => {
      const body: MePatch = { timezone: zone };
      const result = await patch("/v1/me", body);
      if (result.ok) router.refresh();
      return result.ok;
    });

  return (
    <StepFrame
      title={t("title")}
      body={t("body")}
      error={failed}
      action={<SaveButton busy={busy || !zone} onClick={() => void save()} />}
    >
      <Field label={t("label")} hint={browserZone ? t("detected", { zone: browserZone }) : undefined}>
        <Select value={zone} onChange={(event) => setChosen(event.target.value)} className="h-14 text-base">
          {zones.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </Select>
      </Field>
    </StepFrame>
  );
}

/** Language → `PATCH /v1/me/settings`; the BFF sets the `lang` cookie, a refresh switches the UI. */
export function LanguageStep({ onNext, current }: StepProps & { current: Lang | null }) {
  const t = useTranslations("onboarding.language");
  const router = useRouter();
  const [lang, setLang] = useState<Lang>(current ?? "en");
  const { busy, failed, run } = useSave(onNext);

  const save = () =>
    run(async () => {
      const body: SettingsPatch = { lang };
      const result = await patch("/v1/me/settings", body);
      if (result.ok) router.refresh();
      return result.ok;
    });

  return (
    <StepFrame
      title={t("title")}
      body={t("body")}
      error={failed}
      action={<SaveButton busy={busy} onClick={() => void save()} />}
    >
      <ChoiceCards
        legend={t("label")}
        name="lang"
        value={lang}
        onChange={setLang}
        choices={[
          { value: "en", label: t("en"), hint: t("enHint") },
          { value: "tr", label: t("tr"), hint: t("trHint") },
        ]}
      />
    </StepFrame>
  );
}
