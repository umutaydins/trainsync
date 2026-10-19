import { useFormatter, useTranslations } from "next-intl";

import { cn } from "@/lib/cn";

/** A sync older than this shows a warning dot. */
const STALE_MS = 2 * 3600 * 1000;

/** Freshness of `last_synced_at` (rendered on the server, so "ago" matches the moment of the page). */
export function LastSynced({ at, now = new Date() }: { at: string | null | undefined; now?: Date }) {
  const t = useTranslations("sync.freshness");
  const format = useFormatter();
  const stale = at ? now.getTime() - Date.parse(at) > STALE_MS : true;
  return (
    <p className="inline-flex items-center gap-2 text-xs text-muted" data-testid="last-synced">
      <span aria-hidden className={cn("size-2 rounded-full", at ? (stale ? "bg-warn" : "bg-ok") : "bg-surface-3")} />
      {at ? (
        <time dateTime={at} title={format.dateTime(new Date(at), { dateStyle: "medium", timeStyle: "short" })}>
          {t("synced", { ago: format.relativeTime(new Date(at), now) })}
        </time>
      ) : (
        <span>{t("never")}</span>
      )}
    </p>
  );
}
