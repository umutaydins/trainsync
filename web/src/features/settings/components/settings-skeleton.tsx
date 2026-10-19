import { Skeleton } from "@/components/ui/skeleton";

const CARD_HEIGHTS_PX = [96, 220, 160] as const;

/** Loading state of Me's and Admin's pages. */
export function SettingsSkeleton({ label }: { label: string }) {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
      <Skeleton className="h-11 w-20" />
      <Skeleton className="h-10 w-48" label={label} />
      {CARD_HEIGHTS_PX.map((height) => (
        <Skeleton key={height} height={height} className="w-full rounded-card" />
      ))}
    </div>
  );
}
