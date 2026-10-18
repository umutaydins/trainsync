import Link from "next/link";

import { KpiTiles } from "@/components/dashboard/kpi-tiles";
import { SportBreakdown } from "@/components/dashboard/sport-breakdown";
import { CHART_HEIGHT, WeeklyChart } from "@/components/dashboard/weekly-chart";
import { LastSynced } from "@/components/last-synced";
import { Card, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { api, load } from "@/lib/api";
import { formatDate, formatKm, sportLabel } from "@/lib/format";
import type { DashboardRange } from "@/lib/range";

type Props = { range: DashboardRange };

const summary = ({ range }: Props) => load(() => api.summary(range.from, range.to, range.sportType));

export async function KpiBlock(props: Props) {
  const result = await summary(props);
  if (!result.ok) return <ErrorState title="Could not load totals" message={result.error} />;
  return <KpiTiles summary={result.data} />;
}

export function KpiSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {[0, 1, 2, 3].map((i) => (
        <Skeleton key={i} className="h-[92px] rounded-2xl sm:h-[104px]" label={i === 0 ? "Loading totals" : undefined} />
      ))}
    </div>
  );
}

export async function WeeklyBlock({ range }: Props) {
  const result = await load(() => api.weekly(range.from, range.to, range.sportType));
  return (
    <Card title="Weekly volume" labelledBy="weekly-title">
      {!result.ok ? (
        <ErrorState title="Could not load weekly volume" message={result.error} />
      ) : result.data.weeks.every((w) => w.count === 0) ? (
        <div style={{ height: CHART_HEIGHT }} className="flex items-center">
          <div className="w-full"><EmptyState title="No activities in this range">Try a longer range.</EmptyState></div>
        </div>
      ) : (
        <WeeklyChart weeks={result.data.weeks} />
      )}
    </Card>
  );
}

export function WeeklySkeleton() {
  return (
    <Card title="Weekly volume" labelledBy="weekly-title">
      <Skeleton className="mb-3 h-7 w-44" />
      <Skeleton className="w-full" height={CHART_HEIGHT} label="Loading weekly volume" />
      <Skeleton className="mt-3 h-4 w-28" />
    </Card>
  );
}

export async function SportBlock(props: Props) {
  const result = await summary(props);
  return (
    <Card title="By sport" labelledBy="sport-title">
      {result.ok ? <SportBreakdown summary={result.data} /> : <ErrorState title="Could not load sports" message={result.error} />}
    </Card>
  );
}

export async function LongestBlock(props: Props) {
  const result = await summary(props);
  if (!result.ok) return null;
  const longest = result.data.longest;
  return (
    <Card title="Longest activity" labelledBy="longest-title">
      {longest ? (
        <Link href={`/activities/${longest.id}`} className="group block">
          <p className="font-medium group-hover:text-accent">{longest.name}</p>
          <p className="mt-1 text-sm text-muted">
            {sportLabel(longest.sport_type)} · {formatDate(longest.start_date)}
          </p>
          <p className="mt-3 text-2xl font-semibold tabular-nums tracking-tight">{formatKm(longest.distance_m, 1)}</p>
        </Link>
      ) : (
        <EmptyState title="Nothing yet" />
      )}
    </Card>
  );
}

export function CardSkeleton({ title, rows = 4 }: { title: string; rows?: number }) {
  return (
    <Card title={title}>
      <div className="space-y-4">
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-8" label={i === 0 ? `Loading ${title.toLowerCase()}` : undefined} />
        ))}
      </div>
    </Card>
  );
}

export async function LastSyncedBlock(props: Props) {
  const result = await summary(props);
  return <LastSynced at={result.ok ? result.data.last_synced_at : null} />;
}
