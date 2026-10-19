import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { PageTitle } from "@/components/ui/page-header";
import type { EmptyReason } from "@/features/activities/components/activities-empty";
import { ActivityFiltersForm } from "@/features/activities/components/activity-filters";
import { ActivityList } from "@/features/activities/components/activity-list";
import { parseActivityFilters, toApiQuery } from "@/features/activities/query";
import { settingsApi } from "@/features/settings/api";
import { LastSynced } from "@/features/shell/components/last-synced";
import { LoadFailed } from "@/features/shell/components/load-failed";
import { api, load } from "@/lib/api";
import { sportTypes } from "@/lib/sports";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("activities");
  return { title: t("title") };
}

export default async function ActivitiesPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const t = await getTranslations("activities");
  const filters = parseActivityFilters(await searchParams);
  const query = toApiQuery(filters);
  const [page, sports, strava] = await Promise.all([load(() => api.activities(query)), sportTypes(filters.sport_type), load(() => settingsApi.strava())]);
  const filtered = Boolean(filters.from || filters.to || filters.sport_type);
  const emptyReason: EmptyReason = filtered ? "filtered" : strava.ok && !strava.data.connected ? "noStrava" : "notSynced";
  return (
    <>
      <PageTitle title={t("title")} subtitle={t("subtitle")} aside={page.ok ? <LastSynced at={page.data.last_synced_at} /> : null} />
      {emptyReason === "noStrava" && page.ok && page.data.items.length === 0 ? null : <ActivityFiltersForm filters={filters} sports={sports} />}
      {page.ok ? (
        <ActivityList key={JSON.stringify(query)} initial={page.data} query={query} emptyReason={emptyReason} />
      ) : (
        <LoadFailed title={t("failed")} status={page.status} />
      )}
    </>
  );
}
