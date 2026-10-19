import { Badge } from "@/components/ui";
import {
  formatClock,
  formatDateTime,
  formatHeartrate,
  formatKm,
  formatMeters,
  formatPaceOrSpeed,
  paceLabel,
  sportLabel,
} from "@/lib/format";
import type { Activity } from "@/lib/types";

export function ActivityDetailCard({ activity: a }: { activity: Activity }) {
  const stats: [string, string][] = [
    ["Distance", formatKm(a.distance_m)],
    ["Moving time", formatClock(a.moving_time_s)],
    [paceLabel(a.sport_type), formatPaceOrSpeed(a.sport_type, a.distance_m, a.moving_time_s)],
    ["Elevation gain", formatMeters(a.elevation_gain_m)],
    ["Elapsed time", formatClock(a.elapsed_time_s)],
    ["Avg heart rate", formatHeartrate(a.average_heartrate)],
  ];
  return (
    <article
      aria-labelledby="activity-title"
      data-testid="activity-detail"
      className="rounded-2xl border border-border bg-surface p-5 sm:p-7"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="accent">{sportLabel(a.sport_type)}</Badge>
        <time dateTime={a.start_date} className="text-sm text-muted">{formatDateTime(a.start_date)}</time>
      </div>
      <h1 id="activity-title" className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">{a.name}</h1>
      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3">
        {stats.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs font-medium uppercase tracking-wide text-muted">{label}</dt>
            <dd className="mt-1 text-xl font-semibold tabular-nums tracking-tight">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-6 border-t border-border pt-4 text-xs text-muted">
        Strava activity {a.id} · stored {formatDateTime(a.synced_at)}
      </p>
    </article>
  );
}
