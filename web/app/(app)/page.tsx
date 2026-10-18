import { Suspense } from "react";

import {
  CardSkeleton,
  KpiBlock,
  KpiSkeleton,
  LastSyncedBlock,
  LongestBlock,
  SportBlock,
  WeeklyBlock,
  WeeklySkeleton,
} from "@/components/dashboard/blocks";
import { CheckinTilesBlock } from "@/components/checkins/tiles";
import { DashboardFilters } from "@/components/dashboard/filters";
import { TrainingTilesBlock, TrainingTilesSkeleton } from "@/components/dashboard/training-tiles";
import { PageHeader } from "@/components/ui";
import { formatDay, sportLabel } from "@/lib/format";
import { parseRange } from "@/lib/range";
import { sportTypes } from "@/lib/sports";

export const dynamic = "force-dynamic";

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const range = parseRange(await searchParams, new Date());
  const sports = await sportTypes(range.sportType);
  const key = `${range.from}|${range.to}|${range.sportType ?? ""}`;
  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={
          <>
            {formatDay(range.from, true)} – {formatDay(range.to, true)}
            {range.sportType ? ` · ${sportLabel(range.sportType)}` : " · All sports"}
          </>
        }
        aside={
          <Suspense key={key} fallback={<span className="text-xs text-muted">Checking sync…</span>}>
            <LastSyncedBlock range={range} />
          </Suspense>
        }
      />
      <div className="space-y-4">
        <DashboardFilters key={key} range={range} sports={sports} />
        <Suspense key={`kpi-${key}`} fallback={<KpiSkeleton />}>
          <KpiBlock range={range} />
        </Suspense>
        <Suspense fallback={<TrainingTilesSkeleton />}>
          <TrainingTilesBlock />
        </Suspense>
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <Suspense key={`weekly-${key}`} fallback={<WeeklySkeleton />}>
              <WeeklyBlock range={range} />
            </Suspense>
          </div>
          <div className="space-y-4">
            <Suspense key={`sport-${key}`} fallback={<CardSkeleton title="By sport" />}>
              <SportBlock range={range} />
            </Suspense>
            <Suspense key={`longest-${key}`} fallback={<CardSkeleton title="Longest activity" rows={2} />}>
              <LongestBlock range={range} />
            </Suspense>
            <Suspense fallback={<CardSkeleton title="Check-ins" rows={2} />}>
              <CheckinTilesBlock />
            </Suspense>
          </div>
        </div>
      </div>
    </>
  );
}
