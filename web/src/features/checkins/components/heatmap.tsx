import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";

import { cn } from "@/lib/cn";
import type { Checkin } from "@/features/checkins/checkins";
import { STATUSES, STATUS_META, dayLabel, heatmapWeeks, weekdayInitials } from "@/features/checkins/checkins";

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
  const t = useTranslations("checkins");
  const locale = useLocale();
  const weeks = heatmapWeeks(from, to, items);
  return (
    <div>
      <table className="border-separate border-spacing-1" aria-label={t("tableLabel", { from: dayLabel(locale, from), to: dayLabel(locale, to) })}>
        <thead>
          <tr>
            {weekdayInitials(locale).map((d, i) => (
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
                if (!cell.inRange) return <td key={cell.day} aria-hidden="true" className="size-10" />;
                const meta = cell.status ? STATUS_META[cell.status] : null;
                const label = t("cellLabel", { day: dayLabel(locale, cell.day), status: cell.status ? t(`statuses.${cell.status}`) : t("none") });
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
                      className={cn(
                        "flex size-10 items-center justify-center rounded-control text-sm font-bold transition hover:opacity-80",
                        meta ? meta.cell : "bg-surface-2 text-muted",
                        isSelected && "outline-2 outline-offset-2 outline-accent",
                      )}
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
      <ul aria-label={t("legend")} className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted">
        {STATUSES.map((status) => (
          <li key={status} className="flex items-center gap-1.5">
            <span aria-hidden="true" className={cn("flex size-4 items-center justify-center rounded text-[10px] font-semibold", STATUS_META[status].cell)}>
              {STATUS_META[status].glyph}
            </span>
            {t(`statuses.${status}`)}
          </li>
        ))}
        <li className="flex items-center gap-1.5">
          <span aria-hidden="true" className="size-4 rounded bg-surface-2" />
          {t("none")}
        </li>
      </ul>
    </div>
  );
}
