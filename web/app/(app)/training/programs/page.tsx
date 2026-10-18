import type { Metadata } from "next";

import { ProgramBuilder } from "@/components/training/program-builder";
import { ErrorState, PageHeader } from "@/components/ui";
import { load } from "@/lib/api";
import { trainingApi } from "@/lib/training-api";

export const metadata: Metadata = { title: "Programs" };
export const dynamic = "force-dynamic";

export default async function ProgramsPage() {
  const [programs, exercises] = await Promise.all([load(() => trainingApi.programs()), load(() => trainingApi.exercises())]);
  return (
    <>
      <PageHeader title="Programs" subtitle="Generate, edit and activate a training program" />
      {programs.ok ? (
        <ProgramBuilder initial={programs.data.items} exercises={exercises.ok ? exercises.data.items : []} />
      ) : (
        <ErrorState title="Could not load programs" message={programs.error} />
      )}
    </>
  );
}
