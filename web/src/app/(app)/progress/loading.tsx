import { getTranslations } from "next-intl/server";

import { ProgressSkeleton } from "@/features/progress/components/progress-skeleton";

export default async function ProgressLoading() {
  const t = await getTranslations("progress");
  return <ProgressSkeleton label={t("loading")} />;
}
