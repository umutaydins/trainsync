"use client";

import { useLocale, useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { type CardProps, ResetButton, SettingRow, SwitchRow } from "@/features/settings/components/setting-controls";
import { SettingsCard } from "@/features/settings/components/settings-page";
import { useCountries } from "@/features/settings/countries";
import {
  LIMITS,
  changedFields,
  formatQuietHours,
  parseQuietHours,
  sugarLimit,
  toTimeInput,
  wholeNumber,
} from "@/features/settings/settings-form";
import type { SettingsPatch } from "@/features/settings/types";

function SaveRow({ busy, disabled = false }: { busy: boolean; disabled?: boolean }) {
  const common = useTranslations("common.actions");
  return (
    <Button type="submit" size="lg" className="sm:self-start" disabled={busy || disabled}>
      {busy ? common("saving") : common("save")}
    </Button>
  );
}

/** Check-in on/off (saves at once), its time and reminder, the workout reminder, quiet hours. */
export function RemindersCard({ settings, save, busy }: CardProps) {
  const t = useTranslations("settings.coach");
  const quiet = parseQuietHours(settings.quiet_hours);
  const [checkinTime, setCheckinTime] = useState(toTimeInput(settings.checkin_time));
  const [minutes, setMinutes] = useState(String(settings.checkin_reminder_minutes));
  const [workoutTime, setWorkoutTime] = useState(toTimeInput(settings.workout_reminder_time));
  const [quietStart, setQuietStart] = useState(quiet.start);
  const [quietEnd, setQuietEnd] = useState(quiet.end);
  const [invalid, setInvalid] = useState(false);
  const row = { settings, save, busy };

  function submit(event: FormEvent) {
    event.preventDefault();
    const reminder = wholeNumber(minutes, LIMITS.reminderMinutes);
    setInvalid(reminder === null);
    if (reminder === null || !checkinTime || !workoutTime || !quietStart || !quietEnd) return;
    const draft: SettingsPatch = {
      checkin_time: checkinTime,
      checkin_reminder_minutes: reminder,
      workout_reminder_time: workoutTime,
      quiet_hours: formatQuietHours(quietStart, quietEnd),
    };
    void save(changedFields(settings, draft));
  }

  return (
    <SettingsCard id="coach-reminders" title={t("reminders")} body={t("remindersBody")}>
      <SwitchRow label={t("checkinEnabled")} hint={t("checkinEnabledHint")} field="checkin_enabled" {...row} />
      <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <SettingRow label={t("checkinTime")} field="checkin_time" {...row}>
            <Input type="time" required value={checkinTime} onChange={(event) => setCheckinTime(event.target.value)} />
          </SettingRow>
          <SettingRow
            label={t("reminderMinutes")}
            hint={t("reminderMinutesHint", LIMITS.reminderMinutes)}
            error={invalid ? t("reminderMinutesError", LIMITS.reminderMinutes) : undefined}
            field="checkin_reminder_minutes"
            {...row}
          >
            <Input inputMode="numeric" value={minutes} onChange={(event) => setMinutes(event.target.value)} />
          </SettingRow>
        </div>
        <SettingRow label={t("workoutReminder")} hint={t("workoutReminderHint")} field="workout_reminder_time" {...row}>
          <Input type="time" required value={workoutTime} onChange={(event) => setWorkoutTime(event.target.value)} />
        </SettingRow>
        <fieldset className="flex flex-col gap-3" aria-describedby="quiet-hours-hint">
          <legend className="mb-1 font-semibold">{t("quietHours")}</legend>
          <p id="quiet-hours-hint" className="-mt-2 text-sm text-muted">
            {t("quietHoursHint")}
          </p>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              {t("quietFrom")}
              <Input type="time" required value={quietStart} onChange={(event) => setQuietStart(event.target.value)} />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium">
              {t("quietTo")}
              <Input type="time" required value={quietEnd} onChange={(event) => setQuietEnd(event.target.value)} />
            </label>
          </div>
          <div>
            <ResetButton settings={settings} fields={["quiet_hours"]} label={t("quietHours")} save={save} busy={busy} />
          </div>
        </fieldset>
        <SaveRow busy={busy} />
      </form>
    </SettingsCard>
  );
}

/** The daily sugar limit the food pages warn about. */
export function FoodCard({ settings, save, busy }: CardProps) {
  const t = useTranslations("settings.coach");
  const [sugar, setSugar] = useState(String(settings.sugar_limit_g));
  const [invalid, setInvalid] = useState(false);

  function submit(event: FormEvent) {
    event.preventDefault();
    const grams = sugarLimit(sugar);
    setInvalid(grams === null);
    if (grams !== null) void save(changedFields(settings, { sugar_limit_g: grams }));
  }

  return (
    <SettingsCard id="coach-food" title={t("food")}>
      <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
        <SettingRow
          label={t("sugarLimit")}
          error={invalid ? t("sugarLimitError", LIMITS.sugar) : undefined}
          field="sugar_limit_g"
          settings={settings}
          save={save}
          busy={busy}
        >
          <Input inputMode="decimal" value={sugar} onChange={(event) => setSugar(event.target.value)} />
        </SettingRow>
        <SaveRow busy={busy} />
      </form>
    </SettingsCard>
  );
}

/** The country, for the emergency number of the distress reply. */
export function SafetyCard({ settings, save, busy }: CardProps) {
  const t = useTranslations("settings.coach");
  const locale = useLocale();
  const countries = useCountries(locale);
  const [country, setCountry] = useState(settings.country ?? "");
  const known = country === "" || countries.some((c) => c.code === country);

  function submit(event: FormEvent) {
    event.preventDefault();
    void save(changedFields(settings, { country: country || null }));
  }

  return (
    <SettingsCard id="coach-safety" title={t("safety")} body={t("safetyBody")}>
      <form className="flex flex-col gap-4" onSubmit={submit}>
        <SettingRow
          label={t("country")}
          hint={t("emergencyNumber", { number: settings.emergency_number })}
          field="country"
          settings={settings}
          save={save}
          busy={busy}
        >
          <Select value={country} onChange={(event) => setCountry(event.target.value)}>
            <option value="">{t("noCountry")}</option>
            {known ? null : <option value={country}>{country}</option>}
            {countries.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </Select>
        </SettingRow>
        <SaveRow busy={busy} />
      </form>
    </SettingsCard>
  );
}
