import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { SettingsHub } from "@/features/settings/components/settings-hub";
import { api, load } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("nav");
  return { title: t("me") };
}

/** `/me`, the Me tab: the account and its settings pages. */
export default async function MePage() {
  const me = await load(api.me);
  return <SettingsHub me={me.ok ? me.data : null} />;
}
