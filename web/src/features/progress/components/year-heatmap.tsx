"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { type KeyboardEvent, useEffect, useRef, useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { formatDay, formatNumber } from "@/features/progress/format";
import { LEVELS, heatmapGrid, level, moveFocus } from "@/features/progress/heatmap";
import type { Heatmap, HeatmapDay, PeriodQuery } from "@/features/progress/types";
import { progressHref } from "@/features/progress/types";

/** One class per intensity step, from the accent (0 = no training). */
const LEVEL_CLASS = ["bg-surface-3", "bg-accent/25", "bg-accent/50", "bg-accent/75", "bg-accent"] as const;
/** Cell size + gap in px: matches `size-3` and `gap-[3px]` (the month labels are placed with it). */
const CELL_PITCH_PX = 15;
const WEEKDAY_LABEL_ROWS = [0, 2, 4] as const;
const MONDAY = "2024-01-01";
const ISO_DAY_LENGTH = 10;

/**
 * GitHub-style training year: one cell per day, darker = more minutes. A grid for assistive
 * tech (arrow keys move by day and week, every cell has its label); tapping a cell shows its day.
 */
export function YearHeatmap({
  heatmap,
  today,
  firstYear,
  query,
}: {
  heatmap: Heatmap;
  today: string;
  firstYear: number;
  query: PeriodQuery;
}) {
  const t = useTranslations("progress.heatmap");
  const locale = useLocale();
  const grid = heatmapGrid(heatmap.days);
  const ordered = [...heatmap.days].sort((a, b) => a.day.localeCompare(b.day));
  const todayIndex = ordered.findIndex((d) => d.day === today);
  // Today in this year, else its last day (a past year); the parent keys this by year.
  const [focused, setFocused] = useState(todayIndex >= 0 ? todayIndex : Math.max(0, ordered.length - 1));
  const cells = useRef<(HTMLDivElement | null)[]>([]);
  const scroller = useRef<HTMLDivElement>(null);
  const currentYear = Number(today.slice(0, 4));
  const indexOf = new Map(ordered.map((d, i) => [d.day, i]));

  useEffect(() => {
    const cell = cells.current[focused];
    const box = scroller.current;
    if (cell && box) box.scrollLeft = cell.offsetLeft - box.clientWidth / 2;
    // Once: later moves scroll by themselves (focus follows the arrow keys).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const describe = (day: HeatmapDay) => {
    const date = formatDay(locale, day.day, { weekday: "short", day: "numeric", month: "short" });
    const training = day.value > 0 ? t("minutes", { value: formatNumber(locale, day.value), sessions: day.sessions }) : t("rest");
    const checkin = day.checkin ? `, ${t(`checkin.${day.checkin}`)}` : "";
    return `${date}: ${training}${checkin}`;
  };

  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const next = moveFocus(focused, event.key, ordered.length);
    if (next === null) return;
    event.preventDefault();
    setFocused(next);
    cells.current[next]?.focus();
  };

  const active = ordered[focused];
  const yearLink = (year: number) => progressHref({ ...query, year });
  const total = ordered.reduce((sum, d) => sum + (d.value > 0 ? 1 : 0), 0);

  return (
    <div className="flex flex-col gap-3" data-testid="heatmap">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted">{t("activeDays", { count: total })}</p>
        <nav aria-label={t("yearPicker")} className="flex items-center gap-1">
          {heatmap.year > firstYear ? (
            <Link href={yearLink(heatmap.year - 1)} scroll={false} aria-label={t("year", { year: heatmap.year - 1 })} className={buttonVariants({ variant: "ghost", size: "icon" })}>
              <ChevronLeft aria-hidden />
            </Link>
          ) : null}
          <span className="min-w-12 text-center font-bold tabular">
            {heatmap.year}
          </span>
          {heatmap.year < currentYear ? (
            <Link href={yearLink(heatmap.year + 1)} scroll={false} aria-label={t("year", { year: heatmap.year + 1 })} className={buttonVariants({ variant: "ghost", size: "icon" })}>
              <ChevronRight aria-hidden />
            </Link>
          ) : null}
        </nav>
      </div>
      <div ref={scroller} className="overflow-x-auto pb-1">
        <div className="relative inline-flex flex-col gap-1 pl-8">
          <div aria-hidden className="relative h-4" style={{ width: grid.weeks * CELL_PITCH_PX }}>
            {grid.months.map(({ month, week }) => (
              <span key={month} className="absolute top-0 text-[11px] text-muted" style={{ left: week * CELL_PITCH_PX }}>
                {formatDay(locale, `2024-${String(month).padStart(2, "0")}-01`, { month: "short" })}
              </span>
            ))}
          </div>
          <div role="grid" aria-label={t("label", { year: heatmap.year })} onKeyDown={onKey} className="flex flex-col gap-[3px]">
            {grid.rows.map((row, weekday) => (
              <div role="row" key={weekday} className="relative flex gap-[3px]">
                {WEEKDAY_LABEL_ROWS.some((w) => w === weekday) ? (
                  <span aria-hidden className="absolute -left-8 top-1/2 -translate-y-1/2 text-[11px] leading-none text-muted">
                    {formatDay(locale, addDays(MONDAY, weekday), { weekday: "short" })}
                  </span>
                ) : null}
                {row.map((day, week) => {
                  if (!day) return <div key={week} role="gridcell" aria-hidden className="size-3" />;
                  const index = indexOf.get(day.day) ?? 0;
                  const step = level(day.value, heatmap.max_value);
                  return (
                    <div
                      key={day.day}
                      role="gridcell"
                      ref={(node) => {
                        cells.current[index] = node;
                      }}
                      tabIndex={index === focused ? 0 : -1}
                      aria-label={describe(day)}
                      aria-selected={index === focused}
                      data-day={day.day}
                      data-level={step}
                      onClick={() => setFocused(index)}
                      onFocus={() => setFocused(index)}
                      className={cn(
                        "size-3 rounded-[3px] outline-none focus-visible:ring-2 focus-visible:ring-text",
                        LEVEL_CLASS[step],
                        day.day === today && "ring-1 ring-muted",
                        index === focused && "ring-2 ring-text",
                      )}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
      <p aria-live="polite" className="min-h-5 text-sm tabular" data-testid="heatmap-day">
        {active ? describe(active) : null}
      </p>
      <div aria-hidden className="flex items-center gap-1.5 text-[11px] text-muted">
        {t("less")}
        {Array.from({ length: LEVELS + 1 }, (_, step) => (
          <span key={step} className={cn("size-3 rounded-[3px]", LEVEL_CLASS[step])} />
        ))}
        {t("more")}
      </div>
    </div>
  );
}

function addDays(day: string, delta: number): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + delta);
  return date.toISOString().slice(0, ISO_DAY_LENGTH);
}
