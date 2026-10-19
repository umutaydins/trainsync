import type { Metadata } from "next";

import { ActivityFiltersForm } from "@/features/activities/components/activity-filters";
import { ActivityList } from "@/features/activities/components/activity-list";
import { LastSynced } from "@/features/shell/components/last-synced";
import { ErrorState, PageHeader } from "@/components/ui";
import { parseActivityFilters, toApiQuery } from "@/features/activities/query";
import { api, load } from "@/lib/api";
import { sportTypes } from "@/lib/sports";

export const metadata: Metadata = { title: "Activities" };
export const dynamic = "force-dynamic";

export default async function ActivitiesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const filters = parseActivityFilters(await searchParams);
  const query = toApiQuery(filters);
  const [page, sports] = await Promise.all([load(() => api.activities(query)), sportTypes(filters.sport_type)]);
  return (
    <>
      <PageHeader
        title="Activities"
        subtitle="Newest first"
        aside={page.ok ? <LastSynced at={page.data.last_synced_at} /> : null}
      />
      <ActivityFiltersForm filters={filters} sports={sports} />
      {page.ok ? (
        <ActivityList key={JSON.stringify(query)} initial={page.data} query={query} />
      ) : (
        <ErrorState title="Could not load activities" message={page.error} />
      )}
    </>
  );
}
