import Link from "next/link";

import { EmptyState } from "@/components/ui";
import { formatCount, formatDuration, formatKm, sportLabel } from "@/lib/format";
import type { StatsSummary } from "@/lib/types";

/** Totals by sport, biggest moving time first, with a share-of-time bar per row. */
export function SportBreakdown({ summary }: { summary: StatsSummary }) {
  const rows = [...summary.by_sport].sort((a, b) => b.moving_time_s - a.moving_time_s);
  if (rows.length === 0) return <EmptyState title="No activities in this range" />;
  const totalTime = rows.reduce((sum, row) => sum + row.moving_time_s, 0) || 1;
  return (
    <ul className="divide-y divide-border" aria-label="Totals by sport">
      {rows.map((row) => {
        const share = row.moving_time_s / totalTime;
        return (
          <li key={row.sport_type} className="py-3 first:pt-0 last:pb-0">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <Link
                href={`/activities?sport_type=${encodeURIComponent(row.sport_type)}&from=${summary.from}&to=${summary.to}`}
                className="font-medium hover:text-accent"
              >
                {sportLabel(row.sport_type)}
              </Link>
              <span className="tabular-nums text-muted">
                {formatCount(row.count)} · {formatKm(row.distance_m, 1)} · {formatDuration(row.moving_time_s)}
              </span>
            </div>
            <div className="mt-2 h-1.5 rounded-full bg-surface-2" aria-hidden="true">
              <div
                className="h-full rounded-full bg-accent"
                style={{ width: `${Math.max(2, Math.round(share * 100))}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
