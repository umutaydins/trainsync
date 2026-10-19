import { Skeleton } from "@/components/ui";

export default function Loading() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-40" />
      <Skeleton className="h-[62px] rounded-2xl" />
      <Skeleton className="h-[480px] rounded-2xl" label="Loading activities" />
    </div>
  );
}
