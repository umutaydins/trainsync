import Link from "next/link";

import { formatClock, formatDateTime, formatHeartrate, formatKm, formatMeters, formatPaceOrSpeed, sportLabel } from "@/lib/format";
import type { Activity } from "@/lib/types";

const th = "px-3 py-2.5 text-xs font-medium uppercase tracking-wide text-muted";

export function ActivityTable({ items }: { items: Activity[] }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-border bg-surface">
      <table className="w-full min-w-[640px] text-left text-sm" data-testid="activity-table">
        <caption className="sr-only">Activities, newest first</caption>
        <thead className="border-b border-border">
          <tr>
            <th scope="col" className={th}>Date</th>
            <th scope="col" className={th}>Name</th>
            <th scope="col" className={th}>Sport</th>
            <th scope="col" className={`${th} text-right`}>Distance</th>
            <th scope="col" className={`${th} text-right`}>Time</th>
            <th scope="col" className={`${th} text-right`}>Pace / speed</th>
            <th scope="col" className={`${th} hidden text-right md:table-cell`}>Elevation</th>
            <th scope="col" className={`${th} hidden text-right md:table-cell`}>Avg HR</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border tabular-nums">
          {items.map((a) => (
            <tr key={a.id} className="transition hover:bg-surface-2/60" data-activity-id={a.id}>
              <td className="whitespace-nowrap px-3 py-2.5 text-muted">
                <time dateTime={a.start_date}>{formatDateTime(a.start_date)}</time>
              </td>
              <td className="max-w-[16rem] truncate px-3 py-2.5 font-medium">
                <Link href={`/activities/${a.id}`} className="hover:text-accent">{a.name}</Link>
              </td>
              <td className="whitespace-nowrap px-3 py-2.5">{sportLabel(a.sport_type)}</td>
              <td className="whitespace-nowrap px-3 py-2.5 text-right">{formatKm(a.distance_m)}</td>
              <td className="whitespace-nowrap px-3 py-2.5 text-right">{formatClock(a.moving_time_s)}</td>
              <td className="whitespace-nowrap px-3 py-2.5 text-right">{formatPaceOrSpeed(a.sport_type, a.distance_m, a.moving_time_s)}</td>
              <td className="hidden whitespace-nowrap px-3 py-2.5 text-right md:table-cell">{formatMeters(a.elevation_gain_m)}</td>
              <td className="hidden whitespace-nowrap px-3 py-2.5 text-right md:table-cell">{formatHeartrate(a.average_heartrate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
