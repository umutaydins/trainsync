import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { PageTitle } from "@/components/ui/page-header";
import { LoadFailed } from "@/features/shell/components/load-failed";
import { trainingApi } from "@/features/training/api";
import { HistoryList } from "@/features/training/components/history-list";
import { HISTORY_PAGE_SIZE } from "@/features/training/types";
import { load } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("training.history");
  return { title: t("title") };
}

export default async function HistoryPage() {
  const t = await getTranslations("training.history");
  const page = await load(() => trainingApi.workouts(HISTORY_PAGE_SIZE));
  return (
    <>
      <PageTitle title={t("title")} subtitle={t("subtitle")} />
      {page.ok ? <HistoryList initial={page.data} /> : <LoadFailed title={t("loadFailed")} status={page.status} />}
    </>
  );
}
