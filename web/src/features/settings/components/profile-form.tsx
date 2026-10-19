"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { ChoiceCards } from "@/features/onboarding/components/choice-cards";
import { SettingsCard } from "@/features/settings/components/settings-page";
import type { Lang, Me, MePatch, SettingsPatch } from "@/features/settings/types";
import { ThemeSwitch } from "@/features/shell/components/theme-switch";
import { patch } from "@/lib/mutate";
import type { Theme } from "@/lib/theme";
import { useBrowserTimeZones } from "@/lib/time-zones";

/** MePatch's bound. */
export const NAME_MAX_LENGTH = 100;

/** Only what changed, trimmed; null when the name is empty or too long. */
export function profilePatch(me: Pick<Me, "display_name" | "timezone">, name: string, timezone: string): MePatch | null {
  const trimmed = name.trim();
  if (!trimmed || trimmed.length > NAME_MAX_LENGTH) return null;
  const body: MePatch = {};
  if (trimmed !== me.display_name) body.display_name = trimmed;
  if (timezone && timezone !== me.timezone) body.timezone = timezone;
  return body;
}

/** Me → Profile: name and time zone (`PATCH /v1/me`), language (`PATCH /v1/me/settings`), theme. */
export function ProfileForm({ me, lang, theme }: { me: Me | null; lang: Lang | null; theme: Theme }) {
  const t = useTranslations("settings.profile");
  return (
    <>
      {me ? <AccountCard me={me} /> : null}
      {lang ? <LanguageCard initial={lang} /> : null}
      <SettingsCard id="profile-theme" title={t("theme")} body={t("themeBody")}>
        <ThemeSwitch initial={theme} />
      </SettingsCard>
    </>
  );
}

function AccountCard({ me }: { me: Me }) {
  const t = useTranslations("settings.profile");
  const settings = useTranslations("settings");
  const common = useTranslations("common.actions");
  const router = useRouter();
  const toast = useToast();
  const { zones } = useBrowserTimeZones();
  const [saved, setSaved] = useState({ display_name: me.display_name, timezone: me.timezone });
  const [name, setName] = useState(me.display_name);
  const [timezone, setTimezone] = useState(me.timezone);
  const [invalid, setInvalid] = useState(false);
  const [busy, setBusy] = useState(false);
  const options = zones.includes(timezone) ? zones : [timezone, ...zones];

  async function submit(event: FormEvent) {
    event.preventDefault();
    const body = profilePatch(saved, name, timezone);
    setInvalid(body === null);
    if (!body || Object.keys(body).length === 0) return;
    setBusy(true);
    const result = await patch<Me>("/v1/me", body);
    setBusy(false);
    if (!result.ok || !result.data) return toast(settings("saveFailed"), "bad");
    setSaved({ display_name: result.data.display_name, timezone: result.data.timezone });
    toast(settings("saved"), "ok");
    // The BFF refreshed the `tz` cookie: dates re-render in the new zone.
    router.refresh();
  }

  return (
    <SettingsCard id="profile-account" title={t("account")} body={t("signedInAs", { email: me.email })}>
      <form className="flex flex-col gap-4" onSubmit={(event) => void submit(event)} noValidate>
        <Field label={t("name")} error={invalid ? t("nameError", { max: NAME_MAX_LENGTH }) : undefined}>
          <Input
            autoComplete="nickname"
            maxLength={NAME_MAX_LENGTH}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field label={t("timezone")} hint={t("timezoneHint")}>
          <Select value={timezone} onChange={(event) => setTimezone(event.target.value)}>
            {options.map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </Select>
        </Field>
        <Button type="submit" size="lg" className="sm:self-start" disabled={busy}>
          {busy ? common("saving") : common("save")}
        </Button>
      </form>
    </SettingsCard>
  );
}

/** Saves on choice and refreshes, so the whole UI switches language at once. */
function LanguageCard({ initial }: { initial: Lang }) {
  const t = useTranslations("settings.profile");
  const settings = useTranslations("settings");
  const language = useTranslations("onboarding.language");
  const router = useRouter();
  const toast = useToast();
  const [lang, setLang] = useState<Lang>(initial);

  async function choose(next: Lang) {
    const previous = lang;
    setLang(next);
    const body: SettingsPatch = { lang: next };
    const result = await patch("/v1/me/settings", body);
    if (!result.ok) {
      setLang(previous);
      return toast(settings("saveFailed"), "bad");
    }
    // The BFF set the `lang` cookie; the refresh renders every server component in the new language.
    router.refresh();
  }

  return (
    <SettingsCard id="profile-language" title={t("language")} body={t("languageBody")}>
      <ChoiceCards<Lang>
        legend={t("language")}
        name="lang"
        value={lang}
        onChange={(next) => void choose(next)}
        choices={[
          { value: "en", label: language("en"), hint: language("enHint") },
          { value: "tr", label: language("tr"), hint: language("trHint") },
        ]}
      />
    </SettingsCard>
  );
}
