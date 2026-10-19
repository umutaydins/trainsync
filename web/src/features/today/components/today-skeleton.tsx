import { Skeleton } from "@/components/ui/skeleton";

const STATS = 4;
const WORKOUT_PX = 208;
const STAT_PX = 88;
const CARD_PX = 176;

/** Today while it loads: greeting, the workout card, this week's stats, food and activity. */
export function TodaySkeleton({ label }: { label: string }) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <Skeleton className="h-4 w-36" />
      <Skeleton className="h-10 w-64" label={label} />
      <Skeleton height={WORKOUT_PX} className="w-full rounded-card" />
      <div className="grid grid-cols-2 gap-2 rounded-card border border-border bg-surface p-4 sm:grid-cols-4">
        {Array.from({ length: STATS }, (_, i) => (
          <Skeleton key={i} height={STAT_PX} className="w-full" />
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton height={CARD_PX} className="w-full rounded-card" />
        <Skeleton height={CARD_PX} className="w-full rounded-card" />
      </div>
    </div>
  );
}
