import type { Settings, SettingsField, SettingsPatch } from "@/features/settings/types";

/** The API's bounds (SettingsPatch). */
export const LIMITS = {
  reminderMinutes: { min: 0, max: 720 },
  /** Exclusive minimum: a limit of 0 g would flag everything. */
  sugar: { min: 0, max: 1000 },
} as const;

const HH_MM = 5;

/** `21:00:00` → `21:00` (what `<input type="time">` shows and sends). */
export function toTimeInput(value: string): string {
  return value.slice(0, HH_MM);
}

/** `23:00-07:00` → `{start: "23:00", end: "07:00"}`; empty parts for anything else. */
export function parseQuietHours(value: string): { start: string; end: string } {
  const [start = "", end = ""] = value.split("-");
  return { start: toTimeInput(start.trim()), end: toTimeInput(end.trim()) };
}

export function formatQuietHours(start: string, end: string): string {
  return `${start}-${end}`;
}

/** The fields the user set; the others follow the defaults and have nothing to reset. */
export function isCustom(settings: Settings, field: SettingsField): boolean {
  return settings.custom.includes(field);
}

/** `{field: null}`: the API returns the field to its default. */
export function resetPatch(field: SettingsField): SettingsPatch {
  return { [field]: null };
}

/** The current value of a field as the form compares it (times without seconds). */
function comparable(settings: Settings, field: SettingsField): unknown {
  const value = settings[field];
  if (field === "checkin_time" || field === "workout_reminder_time") return toTimeInput(String(value));
  return value;
}

/** Only the fields of `draft` that differ from `settings`: a save never pins an untouched default. */
export function changedFields(settings: Settings, draft: SettingsPatch): SettingsPatch {
  const patch: Record<string, unknown> = {};
  for (const [field, value] of Object.entries(draft) as [SettingsField, unknown][]) {
    if (value !== undefined && value !== comparable(settings, field)) patch[field] = value;
  }
  return patch as SettingsPatch;
}

/** A whole number within `min..max`, or null when the text is not one. */
export function wholeNumber(text: string, { min, max }: { min: number; max: number }): number | null {
  const n = Number(text.trim());
  return text.trim() !== "" && Number.isInteger(n) && n >= min && n <= max ? n : null;
}

/** A sugar limit in grams (decimal comma allowed), above the minimum and at most the maximum. */
export function sugarLimit(text: string): number | null {
  const n = Number(text.trim().replace(",", "."));
  return text.trim() !== "" && Number.isFinite(n) && n > LIMITS.sugar.min && n <= LIMITS.sugar.max ? n : null;
}

/** The typed confirmation matches the word, ignoring case and surrounding spaces (`sil` = `SİL` in tr). */
export function confirmMatches(typed: string, word: string, locale: string): boolean {
  return typed.trim().toLocaleUpperCase(locale) === word.toLocaleUpperCase(locale);
}
