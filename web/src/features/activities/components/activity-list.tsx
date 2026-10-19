"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ActivitiesEmpty, type EmptyReason } from "@/features/activities/components/activities-empty";
import { ActivityTable } from "@/features/activities/components/activity-table";
import { LoadFailed } from "@/features/shell/components/load-failed";
import { bffGet } from "@/lib/bff-get";
import type { Activity, ActivityPage } from "@/lib/types";

/** Keyset paging: "Load more" asks the BFF for the page after `next_cursor` and appends it. */
export function ActivityList({
  initial,
  query,
  emptyReason = "filtered",
}: {
  initial: ActivityPage;
  query: Record<string, string>;
  emptyReason?: EmptyReason;
}) {
  const t = useTranslations("activities.list");
  const common = useTranslations("common");
  const [items, setItems] = useState<Activity[]>(initial.items);
  const [cursor, setCursor] = useState<string | null>(initial.next_cursor);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState<number | null>(null);

  async function loadMore() {
    if (!cursor || loading) return;
    setLoading(true);
    setFailed(null);
    const result = await bffGet<ActivityPage>("/v1/activities", { ...query, cursor });
    setLoading(false);
    if (!result.ok || !result.data) return setFailed(result.status);
    const page = result.data;
    setItems((current) => {
      const seen = new Set(current.map((a) => a.id));
      return [...current, ...page.items.filter((a) => !seen.has(a.id))];
    });
    setCursor(page.next_cursor);
  }

  if (items.length === 0) return <ActivitiesEmpty reason={emptyReason} />;

  return (
    <div className="flex flex-col gap-4">
      <ActivityTable items={items} />
      {failed !== null ? <LoadFailed title={t("moreFailed")} status={failed} /> : null}
      <div className="flex items-center justify-between gap-3 text-sm text-muted">
        <p aria-live="polite">{t("showing", { count: items.length })}</p>
        {cursor ? (
          <Button variant="secondary" onClick={() => void loadMore()} disabled={loading}>
            {loading ? common("states.loading") : failed !== null ? common("actions.retry") : common("actions.loadMore")}
          </Button>
        ) : (
          <p>{common("actions.endOfList")}</p>
        )}
      </div>
    </div>
  );
}
