import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { DeleteAccountCard, ExportCard } from "@/features/settings/components/data-cards";
import { SettingsPage } from "@/features/settings/components/settings-page";
import { api, load } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("settings.sections.data");
  return { title: t("title") };
}

/** `/me/data`: Export and Delete account (named so in the privacy policy and the terms). */
export default async function DataPage() {
  const t = await getTranslations("settings");
  const me = await load(api.me);
  return (
    <SettingsPage title={t("sections.data.title")} subtitle={t("sections.data.hint")}>
      <ExportCard />
      <DeleteAccountCard isOwner={me.ok && me.data.role === "owner"} />
    </SettingsPage>
  );
}
