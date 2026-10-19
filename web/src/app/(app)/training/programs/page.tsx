import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { PageTitle } from "@/components/ui/page-header";
import { LoadFailed } from "@/features/shell/components/load-failed";
import { trainingApi } from "@/features/training/api";
import { ProgramBuilder } from "@/features/training/components/program-builder";
import { load } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("training.programs");
  return { title: t("title") };
}

export default async function ProgramsPage() {
  const t = await getTranslations("training.programs");
  const [programs, exercises] = await Promise.all([load(() => trainingApi.programs()), load(() => trainingApi.exercises())]);
  return (
    <>
      <PageTitle title={t("title")} subtitle={t("subtitle")} />
      {programs.ok ? (
        <ProgramBuilder initial={programs.data.items} exercises={exercises.ok ? exercises.data.items : []} />
      ) : (
        <LoadFailed title={t("loadFailed")} status={programs.status} />
      )}
    </>
  );
}
