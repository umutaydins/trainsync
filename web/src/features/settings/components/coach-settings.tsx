"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { VoicePicker, type Voice } from "@/features/onboarding/components/voice-picker";
import { FoodCard, RemindersCard, SafetyCard } from "@/features/settings/components/reminder-cards";
import { type CardProps, ResetButton, SwitchRow, useSettings } from "@/features/settings/components/setting-controls";
import { SettingsCard } from "@/features/settings/components/settings-page";
import { changedFields } from "@/features/settings/settings-form";
import type { Settings } from "@/features/settings/types";

/** A card's draft starts over whenever its saved values change (after a save or a reset). */
const keyOf = (settings: Settings, fields: readonly (keyof Settings)[]) =>
  fields.map((field) => String(settings[field])).join("|");

/**
 * Me → Coach & reminders: every field of `SettingsOut` except language (Profile) and the zone
 * (`PATCH /v1/me`). Each card saves only what changed; "Default" sends null for a field.
 */
export function CoachSettings({ initial }: { initial: Settings }) {
  const { settings, busy, save } = useSettings(initial);
  const props = { settings, save, busy };
  return (
    <>
      <VoiceCard key={keyOf(settings, ["tone", "intensity", "profanity"])} {...props} />
      <RemindersCard
        key={keyOf(settings, ["checkin_time", "checkin_reminder_minutes", "workout_reminder_time", "quiet_hours"])}
        {...props}
      />
      <DigestsCard {...props} />
      <FoodCard key={keyOf(settings, ["sugar_limit_g"])} {...props} />
      <SafetyCard key={keyOf(settings, ["country"])} {...props} />
    </>
  );
}

function VoiceCard({ settings, save, busy }: CardProps) {
  const t = useTranslations("settings.coach");
  const common = useTranslations("common.actions");
  const [voice, setVoice] = useState<Voice>({
    tone: settings.tone,
    intensity: settings.intensity,
    profanity: settings.profanity,
  });
  const changes = changedFields(settings, voice);
  return (
    <SettingsCard id="coach-voice" title={t("voice")} body={t("voiceBody")}>
      <VoicePicker voice={voice} onChange={setVoice} />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="lg"
          disabled={busy || Object.keys(changes).length === 0}
          onClick={() => void save(changes)}
        >
          {busy ? common("saving") : common("save")}
        </Button>
        <ResetButton
          settings={settings}
          fields={["tone", "intensity", "profanity"]}
          label={t("voice")}
          save={save}
          busy={busy}
        />
      </div>
    </SettingsCard>
  );
}

function DigestsCard({ settings, save, busy }: CardProps) {
  const t = useTranslations("settings.coach");
  return (
    <SettingsCard id="coach-digests" title={t("digests")}>
      <SwitchRow
        label={t("digestsSwitch")}
        hint={t("digestsHint")}
        field="stats_digest_enabled"
        settings={settings}
        save={save}
        busy={busy}
      />
    </SettingsCard>
  );
}
