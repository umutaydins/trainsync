import type { Metadata } from "next";

import { HistoryList } from "@/components/training/history-list";
import { ErrorState, PageHeader } from "@/components/ui";
import { load } from "@/lib/api";
import { trainingApi } from "@/lib/training-api";
import { HISTORY_PAGE_SIZE } from "@/lib/training-types";

export const metadata: Metadata = { title: "Workout history" };
export const dynamic = "force-dynamic";

export default async function HistoryPage() {
  const page = await load(() => trainingApi.workouts(HISTORY_PAGE_SIZE));
  return (
    <>
      <PageHeader title="History" subtitle="Workouts, newest first" />
      {page.ok ? <HistoryList initial={page.data} /> : <ErrorState title="Could not load workouts" message={page.error} />}
    </>
  );
}
