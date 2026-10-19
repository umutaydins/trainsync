import { getTranslations } from "next-intl/server";

import { Skeleton } from "@/components/ui/skeleton";

const LIST_PX = 160;
const FORM_PX = 320;

export default async function ProgramsLoading() {
  const t = await getTranslations("training.programs");
  return (
    <div className="flex flex-col gap-4">
      <Skeleton className="h-10 w-48" label={t("loading")} />
      <Skeleton height={LIST_PX} className="w-full rounded-card" />
      <Skeleton height={FORM_PX} className="w-full rounded-card" />
    </div>
  );
}
