import { formatAgo, formatDateTime } from "@/lib/format";

/** Freshness indicator for `last_synced_at` (server-rendered, so "ago" never mismatches on hydrate). */
export function LastSynced({ at, now = new Date() }: { at: string | null | undefined; now?: Date }) {
  const stale = at ? now.getTime() - new Date(at).getTime() > 2 * 3600 * 1000 : true;
  return (
    <p className="inline-flex items-center gap-2 text-xs text-muted" data-testid="last-synced">
      <span
        aria-hidden="true"
        className={`size-2 rounded-full ${at ? (stale ? "bg-warn" : "bg-ok") : "bg-border"}`}
      />
      {at ? (
        <span>
          Last synced <time dateTime={at} title={formatDateTime(at)}>{formatAgo(at, now)}</time>
        </span>
      ) : (
        <span>Not synced yet</span>
      )}
    </p>
  );
}
