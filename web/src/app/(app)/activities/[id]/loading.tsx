import { Skeleton } from "@/components/ui";

export default function Loading() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-5 w-24" />
      <Skeleton className="h-[340px] rounded-2xl" label="Loading activity" />
    </div>
  );
}
