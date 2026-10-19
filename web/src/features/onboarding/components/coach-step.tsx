"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { SaveButton, StepFrame, type StepProps, useSave } from "@/features/onboarding/components/step-frame";
import { VoicePicker, type Voice } from "@/features/onboarding/components/voice-picker";
import type { SettingsPatch } from "@/features/onboarding/types";
import { patch } from "@/lib/mutate";

const DEFAULT_VOICE: Voice = { tone: "neutral", intensity: "normal", profanity: "roast" };

/** Coach voice with a live sample line → `PATCH /v1/me/settings`. */
export function CoachStep({ onNext, current }: StepProps & { current: Voice | null }) {
  const t = useTranslations("onboarding.coach");
  const [voice, setVoice] = useState<Voice>(() =>
    current ? { tone: current.tone, intensity: current.intensity, profanity: current.profanity } : DEFAULT_VOICE,
  );
  const { busy, failed, run } = useSave(onNext);

  const save = () =>
    run(async () => {
      // Only the voice: the language may have just changed in the previous step.
      const body: SettingsPatch = { tone: voice.tone, intensity: voice.intensity, profanity: voice.profanity };
      return (await patch("/v1/me/settings", body)).ok;
    });

  return (
    <StepFrame
      title={t("title")}
      body={t("body")}
      error={failed}
      action={<SaveButton busy={busy} onClick={() => void save()} />}
    >
      <VoicePicker voice={voice} onChange={setVoice} />
    </StepFrame>
  );
}
