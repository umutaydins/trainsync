import { CheckCircle2, Link2 } from "lucide-react";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { Button } from "@/components/ui/button";
import { PageTitle } from "@/components/ui/page-header";
import { Failure } from "@/components/ui/states";
import { LastSynced } from "@/features/shell/components/last-synced";
import { LoadFailed } from "@/features/shell/components/load-failed";
import { STRAVA_CONNECT_URL } from "@/features/sync/components/sync-cards";
import { SyncStatusView } from "@/features/sync/components/sync-status-view";
import { api, load } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("sync");
  return { title: t("title") };
}

export default async function SyncPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const t = await getTranslations("sync");
  const params = await searchParams;
  const [result, me] = await Promise.all([load(() => api.syncStatus()), load(api.me)]);
  // Only the owner sees a failed run's technical error text (the API leaves it out for others).
  const isOwner = me.ok && me.data.role === "owner";
  const connected = result.ok && result.data.athletes.length > 0;
  return (
    <>
      <PageTitle
        title={t("title")}
        subtitle={result.ok ? <LastSynced at={result.data.last_synced_at} /> : t("subtitle")}
        aside={
          <Button asChild variant={connected ? "secondary" : "primary"}>
            <a href={STRAVA_CONNECT_URL}>
              <Link2 aria-hidden />
              {t("connect")}
            </a>
          </Button>
        }
      />
      <div className="flex flex-col gap-4">
        {params.connected === "1" ? (
          <p role="status" data-testid="strava-connected" className="flex items-center gap-2 rounded-card border border-ok/30 bg-ok-soft p-4 text-sm font-medium text-ok">
            <CheckCircle2 aria-hidden className="size-5" />
            {t("connected")}
          </p>
        ) : null}
        {typeof params.connect_error === "string" ? <Failure title={t("connectFailed")} message={t("connectFailedHint")} /> : null}
        {result.ok ? <SyncStatusView initial={result.data} isOwner={isOwner} /> : <LoadFailed title={t("failed")} status={result.status} />}
      </div>
    </>
  );
}
