"use client";

import { RotateCcw } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCallback, useState, type ReactElement, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { isCustom, resetPatch } from "@/features/settings/settings-form";
import type { Settings, SettingsField, SettingsPatch } from "@/features/settings/types";
import { patch } from "@/lib/mutate";

export type SaveSettings = (body: SettingsPatch) => Promise<boolean>;

/** What every card of Coach & reminders gets. */
export interface CardProps {
  settings: Settings;
  save: SaveSettings;
  busy: boolean;
}

/** The effective settings and a `PATCH /v1/me/settings` that adopts the API's answer. */
export function useSettings(initial: Settings) {
  const t = useTranslations("settings");
  const toast = useToast();
  const [settings, setSettings] = useState(initial);
  const [busy, setBusy] = useState(false);
  const save = useCallback<SaveSettings>(
    async (body) => {
      if (Object.keys(body).length === 0) return true;
      setBusy(true);
      const result = await patch<Settings>("/v1/me/settings", body);
      setBusy(false);
      if (!result.ok || !result.data) {
        toast(t("saveFailed"), "bad");
        return false;
      }
      setSettings(result.data);
      toast(t("saved"), "ok");
      return true;
    },
    [t, toast],
  );
  return { settings, busy, save };
}

/** "Default": sends `{field: null}`; shown only for a field the user changed. */
export function ResetButton({
  settings,
  fields,
  label,
  save,
  busy,
}: {
  settings: Settings;
  fields: readonly SettingsField[];
  label: string;
  save: SaveSettings;
  busy: boolean;
}) {
  const t = useTranslations("settings");
  if (!fields.some((field) => isCustom(settings, field))) return null;
  const body = Object.assign({}, ...fields.map(resetPatch)) as SettingsPatch;
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      aria-label={t("resetLabel", { field: label })}
      disabled={busy}
      onClick={() => void save(body)}
    >
      <RotateCcw aria-hidden />
      {t("default")}
    </Button>
  );
}

/** A labelled control with its reset button. */
export function SettingRow({
  label,
  hint,
  error,
  field,
  settings,
  save,
  busy,
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: ReactNode;
  field: SettingsField;
  settings: Settings;
  save: SaveSettings;
  busy: boolean;
  children: ReactElement<Record<string, unknown>>;
}) {
  return (
    <div className="flex items-start gap-2">
      <Field label={label} hint={hint} error={error} className="min-w-0 flex-1">
        {children}
      </Field>
      <div className="pt-7">
        <ResetButton settings={settings} fields={[field]} label={label} save={save} busy={busy} />
      </div>
    </div>
  );
}

/** An on/off setting that saves at once. */
export function SwitchRow({
  label,
  hint,
  field,
  settings,
  save,
  busy,
}: {
  label: string;
  hint: string;
  field: "checkin_enabled" | "stats_digest_enabled";
  settings: Settings;
  save: SaveSettings;
  busy: boolean;
}) {
  const id = `switch-${field}`;
  return (
    <div className="flex items-center gap-4">
      <div className="min-w-0 flex-1">
        <label htmlFor={id} className="font-semibold">
          {label}
        </label>
        <p id={`${id}-hint`} className="text-sm text-muted">
          {hint}
        </p>
      </div>
      <ResetButton settings={settings} fields={[field]} label={label} save={save} busy={busy} />
      <Switch
        id={id}
        aria-describedby={`${id}-hint`}
        checked={settings[field]}
        disabled={busy}
        onCheckedChange={(checked) => void save({ [field]: checked })}
      />
    </div>
  );
}
