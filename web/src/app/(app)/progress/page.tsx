import type { Metadata } from "next";
import { getTimeZone, getTranslations } from "next-intl/server";

import { ProgressView } from "@/features/progress/components/progress-view";
import { localDay } from "@/features/progress/format";
import { loadProgress } from "@/features/progress/load";
import { parsePeriod } from "@/features/progress/types";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("progress");
  return { title: t("title") };
}

/** `/progress?period=…&from=…&to=…&lift=…&year=…`: shareable and rendered on the server. */
export default async function ProgressPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = parsePeriod(await searchParams);
  const today = localDay(new Date(), await getTimeZone());
  return <ProgressView data={await loadProgress(query, today)} />;
}
