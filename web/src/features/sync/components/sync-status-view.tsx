"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { LoadFailed } from "@/features/shell/components/load-failed";
import { Circuit, RateLimits, SyncRuns, Webhooks } from "@/features/sync/components/sync-cards";
import type { SyncStatus } from "@/lib/types";

export const REFRESH_MS = 15_000;
const MS_PER_S = 1000;

/** Sync health, refreshed from the BFF every 15 s. Keeps the last good data if a refresh fails. */
export function SyncStatusView({ initial, intervalMs = REFRESH_MS }: { initial: SyncStatus; intervalMs?: number }) {
  const t = useTranslations("sync");
  const format = useFormatter();
  const [status, setStatus] = useState(initial);
  const [failed, setFailed] = useState<number | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;
    const timer = setInterval(async () => {
      let response: Response;
      try {
        response = await fetch("/api/ts/v1/sync/status", { cache: "no-store" });
      } catch {
        if (!cancelled) setFailed(0);
        return;
      }
      const body: unknown = await response.json().catch(() => null);
      if (cancelled) return;
      if (!response.ok || !body) return setFailed(response.status);
      setStatus(body as SyncStatus);
      setFailed(null);
      setUpdatedAt(new Date());
    }, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [intervalMs]);

  return (
    <div className="flex flex-col gap-4" data-testid="sync-status">
      <p className="text-xs text-muted" aria-live="polite">
        {t("refresh", { seconds: Math.round(intervalMs / MS_PER_S) })}
        {updatedAt ? ` · ${t("updated", { time: format.dateTime(updatedAt, { timeStyle: "medium" }) })}` : ""}
      </p>
      {failed !== null ? <LoadFailed title={t("refreshFailed")} status={failed} /> : null}
      <SyncRuns status={status} />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Webhooks status={status} />
        <RateLimits status={status} />
        <Circuit status={status} />
      </div>
    </div>
  );
}
