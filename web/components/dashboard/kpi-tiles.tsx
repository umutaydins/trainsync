import { StatTile } from "@/components/ui";
import { formatCount, formatDuration, formatKm, formatMeters } from "@/lib/format";
import type { StatsSummary } from "@/lib/types";

export function KpiTiles({ summary }: { summary: StatsSummary }) {
  const { totals } = summary;
  return (
    <dl
      aria-label="Totals"
      data-testid="kpis"
      data-from={summary.from}
      data-to={summary.to}
      className="grid grid-cols-2 gap-3 lg:grid-cols-4"
    >
      <StatTile label="Distance" value={formatKm(totals.distance_m, 1)} />
      <StatTile label="Moving time" value={formatDuration(totals.moving_time_s)} hint="h:mm" />
      <StatTile label="Elevation" value={formatMeters(totals.elevation_gain_m)} />
      <StatTile label="Activities" value={formatCount(totals.count)} />
    </dl>
  );
}
