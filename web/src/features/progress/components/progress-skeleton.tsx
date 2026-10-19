import { Skeleton } from "@/components/ui/skeleton";
import { CHART_HEIGHT } from "@/features/progress/components/chart-kit";

const STATS_PER_BLOCK = 4;
const SMALL_BLOCKS = 6;
const STAT_PX = 88;

/** The progress screen while it loads: the switcher, the volume chart, then the blocks' cards. */
export function ProgressSkeleton({ label }: { label: string }) {
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-10 w-40" label={label} />
      <Skeleton className="h-4 w-56" />
      <Skeleton className="h-11 w-full rounded-full" />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-4 rounded-card border border-border bg-surface p-4 lg:col-span-2">
          <Skeleton className="h-6 w-32" />
          <Skeleton height={CHART_HEIGHT} className="w-full" />
        </div>
        {Array.from({ length: SMALL_BLOCKS }, (_, block) => (
          <div key={block} className="flex flex-col gap-4 rounded-card border border-border bg-surface p-4">
            <Skeleton className="h-6 w-32" />
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {Array.from({ length: STATS_PER_BLOCK }, (_, stat) => (
                <Skeleton key={stat} height={STAT_PX} className="w-full" />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
