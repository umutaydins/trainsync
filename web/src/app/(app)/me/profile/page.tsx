import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { Failure } from "@/components/ui/states";
import { currentTheme, settingsApi } from "@/features/settings/api";
import { ProfileForm } from "@/features/settings/components/profile-form";
import { SettingsPage } from "@/features/settings/components/settings-page";
import { api, load } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("settings.sections.profile");
  return { title: t("title") };
}

/** `/me/profile`: name, time zone, language, theme. */
export default async function ProfilePage() {
  const t = await getTranslations("settings");
  const [me, settings, theme] = await Promise.all([load(api.me), load(settingsApi.settings), currentTheme()]);
  return (
    <SettingsPage title={t("sections.profile.title")} subtitle={t("sections.profile.hint")}>
      {me.ok && settings.ok ? null : <Failure title={t("loadFailed")} />}
      <ProfileForm me={me.ok ? me.data : null} lang={settings.ok ? settings.data.lang : null} theme={theme} />
    </SettingsPage>
  );
}
