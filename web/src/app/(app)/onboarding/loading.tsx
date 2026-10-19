import { Skeleton } from "@/components/ui/skeleton";

const LOADING_HEIGHT_PX = 320;

export default function OnboardingLoading() {
  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-6">
      <Skeleton className="mx-auto h-8 w-40" />
      <Skeleton className="h-10 w-3/4" />
      <Skeleton height={LOADING_HEIGHT_PX} className="w-full rounded-card" />
    </div>
  );
}
