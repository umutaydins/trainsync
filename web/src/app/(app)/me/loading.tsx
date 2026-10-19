import { getTranslations } from "next-intl/server";

import { SettingsSkeleton } from "@/features/settings/components/settings-skeleton";

export default async function MeLoading() {
  const t = await getTranslations("common.states");
  return <SettingsSkeleton label={t("loading")} />;
}
