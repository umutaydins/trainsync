import { getTranslations } from "next-intl/server";

import { Skeleton } from "@/components/ui/skeleton";

export default async function WorkoutLoading() {
  const t = await getTranslations("workout");
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
      <Skeleton className="h-10 w-48" />
      <Skeleton className="h-16 w-full rounded-card" />
      <Skeleton className="h-96 w-full rounded-card" label={t("loading")} />
    </div>
  );
}
