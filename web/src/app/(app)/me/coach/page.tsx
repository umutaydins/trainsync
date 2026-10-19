import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { Failure } from "@/components/ui/states";
import { settingsApi } from "@/features/settings/api";
import { CoachSettings } from "@/features/settings/components/coach-settings";
import { SettingsPage } from "@/features/settings/components/settings-page";
import { load } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("settings.sections.coach");
  return { title: t("title") };
}

/** `/me/coach`: the coach's voice, check-in and reminders, digests, sugar limit, country. */
export default async function CoachPage() {
  const t = await getTranslations("settings");
  const settings = await load(settingsApi.settings);
  return (
    <SettingsPage title={t("sections.coach.title")} subtitle={t("sections.coach.hint")}>
      {settings.ok ? <CoachSettings initial={settings.data} /> : <Failure title={t("loadFailed")} />}
    </SettingsPage>
  );
}
