import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { Failure } from "@/components/ui/states";
import { stravaReturnFrom } from "@/features/onboarding/steps";
import { settingsApi } from "@/features/settings/api";
import { StravaCard, TelegramCard } from "@/features/settings/components/connection-cards";
import { SettingsPage } from "@/features/settings/components/settings-page";
import { load } from "@/lib/api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("settings.sections.connections");
  return { title: t("title") };
}

/** `/me/connections`: Strava and Telegram. Strava's OAuth comes back here (`?connected=1`). */
export default async function ConnectionsPage({ searchParams }: { searchParams: SearchParams }) {
  const t = await getTranslations("settings");
  const [strava, telegram] = await Promise.all([load(settingsApi.strava), load(settingsApi.telegram)]);
  const returned = stravaReturnFrom(await searchParams);
  return (
    <SettingsPage title={t("sections.connections.title")} subtitle={t("sections.connections.hint")}>
      {strava.ok ? (
        <StravaCard initial={strava.data} returned={returned} />
      ) : (
        <Failure title={t("connections.loadFailed", { name: t("connections.strava") })} />
      )}
      {telegram.ok ? (
        <TelegramCard initial={telegram.data} />
      ) : (
        <Failure title={t("connections.loadFailed", { name: t("connections.telegram") })} />
      )}
    </SettingsPage>
  );
}
