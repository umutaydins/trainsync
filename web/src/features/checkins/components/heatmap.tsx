import Link from "next/link";

import type { Checkin } from "@/features/checkins/checkins";
import { STATUSES, STATUS_META, dayLabel, heatmapWeeks } from "@/features/checkins/checkins";

const WEEKDAYS = ["M", "T", "W", "T", "F", "S", "S"];

/**
 * Calendar heatmap of check-ins: one row per ISO week, Monday first. Every cell carries a glyph
 * and an accessible label besides its colour, and links to that day's editor (`?day=`).
 */
export function CheckinHeatmap({
  from,
  to,
  items,
  selected,
}: {
  from: string;
  to: string;
  items: readonly Checkin[];
  selected?: string;
}) {
  const weeks = heatmapWeeks(from, to, items);
  return (
    <div>
      <table className="border-separate border-spacing-1" aria-label={`Check-ins ${from} to ${to}`}>
        <thead>
          <tr>
            {WEEKDAYS.map((d, i) => (
              <th key={i} scope="col" className="text-center text-xs font-medium text-muted">
                {d}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week) => (
            <tr key={week[0]?.day}>
              {week.map((cell) => {
                if (!cell.inRange) return <td key={cell.day} aria-hidden="true" className="size-8 sm:size-9" />;
                const meta = cell.status ? STATUS_META[cell.status] : null;
                const label = `${dayLabel(cell.day)}: ${meta ? meta.label : "No check-in"}`;
                const isSelected = cell.day === selected;
                return (
                  <td key={cell.day} className="p-0">
                    <Link
                      href={`?day=${cell.day}`}
                      aria-label={label}
                      title={label}
                      aria-current={isSelected ? "date" : undefined}
                      data-day={cell.day}
                      data-status={cell.status ?? "none"}
                      className={`flex size-8 items-center justify-center rounded-md text-xs font-semibold transition hover:opacity-80 sm:size-9 ${
                        meta ? meta.cell : "bg-surface-2 text-muted"
                      } ${isSelected ? "outline-2 outline-offset-1 outline-text" : ""}`}
                    >
                      <span aria-hidden="true">{meta ? meta.glyph : ""}</span>
                    </Link>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <ul aria-label="Legend" className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {STATUSES.map((status) => (
          <li key={status} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className={`flex size-4 items-center justify-center rounded text-[10px] font-semibold ${STATUS_META[status].cell}`}
            >
              {STATUS_META[status].glyph}
            </span>
            {STATUS_META[status].label}
          </li>
        ))}
        <li className="flex items-center gap-1.5">
          <span aria-hidden="true" className="size-4 rounded bg-surface-2" />
          No check-in
        </li>
      </ul>
    </div>
  );
}
