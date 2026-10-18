"use client";

import { useState } from "react";

import { ActivityTable } from "@/components/activities/activity-table";
import { EmptyState, ErrorState, secondaryButtonClass } from "@/components/ui";
import { formatCount } from "@/lib/format";
import type { Activity, ActivityPage } from "@/lib/types";

/** Keyset paging: "Load more" asks the BFF for the page after `next_cursor` and appends it. */
export function ActivityList({ initial, query }: { initial: ActivityPage; query: Record<string, string> }) {
  const [items, setItems] = useState<Activity[]>(initial.items);
  const [cursor, setCursor] = useState<string | null>(initial.next_cursor);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadMore() {
    if (!cursor || loading) return;
    setLoading(true);
    setError(null);
    try {
      const search = new URLSearchParams({ ...query, cursor });
      const response = await fetch(`/api/ts/v1/activities?${search}`, { cache: "no-store" });
      const body: unknown = await response.json().catch(() => null);
      if (!response.ok) {
        const message = (body as { error?: string } | null)?.error;
        throw new Error(message || `request failed (${response.status})`);
      }
      const page = body as ActivityPage;
      setItems((current) => {
        const seen = new Set(current.map((a) => a.id));
        return [...current, ...page.items.filter((a) => !seen.has(a.id))];
      });
      setCursor(page.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "request failed");
    } finally {
      setLoading(false);
    }
  }

  if (items.length === 0) {
    return <EmptyState title="No activities match these filters">Change the dates or the sport.</EmptyState>;
  }

  return (
    <div className="space-y-4">
      <ActivityTable items={items} />
      {error ? <ErrorState title="Could not load more activities" message={error} /> : null}
      <div className="flex items-center justify-between gap-3 text-sm text-muted">
        <p aria-live="polite">Showing {formatCount(items.length)} {items.length === 1 ? "activity" : "activities"}</p>
        {cursor ? (
          <button type="button" onClick={loadMore} disabled={loading} className={secondaryButtonClass}>
            {loading ? "Loading…" : error ? "Retry" : "Load more"}
          </button>
        ) : (
          <p>End of list</p>
        )}
      </div>
    </div>
  );
}
