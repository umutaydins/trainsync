import type { Metadata } from "next";

import { LastSynced } from "@/features/shell/components/last-synced";
import { SyncStatusView } from "@/features/sync/components/sync-status-view";
import { ErrorState, PageHeader, buttonClass } from "@/components/ui";
import { api, load } from "@/lib/api";
import { serverEnv } from "@/lib/env";

export const metadata: Metadata = { title: "Sync" };
export const dynamic = "force-dynamic";

/** The browser goes to the API's OAuth login; the API sends it back here (`return_to`). */
function connectUrl(): string {
  const env = serverEnv();
  const returnTo = `${env.publicWebUrl}/sync`;
  return `${env.publicApiUrl}/auth/strava/login?${new URLSearchParams({ return_to: returnTo })}`;
}

export default async function SyncPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const result = await load(() => api.syncStatus());
  return (
    <>
      <PageHeader
        title="Sync"
        subtitle={result.ok ? <LastSynced at={result.data.last_synced_at} /> : "Strava sync health"}
        aside={
          <a href={connectUrl()} className={buttonClass}>
            Connect Strava
          </a>
        }
      />
      {params.connected === "1" ? (
        <p role="status" className="mb-4 rounded-xl border border-ok/30 bg-ok-soft px-4 py-3 text-sm text-ok">
          Strava connected. The backfill is queued and shows up below.
        </p>
      ) : null}
      {typeof params.connect_error === "string" ? (
        <div className="mb-4">
          <ErrorState title="Connecting Strava failed" message={params.connect_error} />
        </div>
      ) : null}
      {result.ok ? (
        <SyncStatusView initial={result.data} />
      ) : (
        <ErrorState title="Could not load sync status" message={result.error} />
      )}
    </>
  );
}
