import { useFormatter, useTranslations } from "next-intl";

import { cn } from "@/lib/cn";
import { PlannedWorkout } from "@/features/today/components/planned-workout";
import { FoodToday, LatestActivity, WeekGlance } from "@/features/today/components/today-blocks";
import type { TodayData } from "@/features/today/load";

/** A sync older than this shows a warning dot. */
const STALE_MS = 2 * 3600 * 1000;
const MORNING_FROM = 5;
const AFTERNOON_FROM = 12;
const EVENING_FROM = 18;

type DayPart = "morning" | "afternoon" | "evening";

export function dayPart(hour: number): DayPart {
  if (hour >= MORNING_FROM && hour < AFTERNOON_FROM) return "morning";
  if (hour >= AFTERNOON_FROM && hour < EVENING_FROM) return "afternoon";
  return "evening";
}

/** `/`, the Today tab: greeting, today's workout, this week, today's food, the latest activity. */
export function TodayView({ data }: { data: TodayData }) {
  const t = useTranslations("today");
  const format = useFormatter();
  const name = data.me.ok ? data.me.data.display_name.trim().split(/\s+/)[0] : "";
  const date = format.dateTime(new Date(`${data.today}T12:00:00Z`), { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
  const syncedAt = data.latest.ok ? data.latest.data.last_synced_at : null;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4" data-testid="today">
      <header className="mb-1 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold uppercase tracking-[0.08em] text-accent-ink">{date}</p>
          <h1 className="text-3xl font-black tracking-tight sm:text-4xl">
            {name ? t(`greeting.${dayPart(data.hour)}`, { name }) : t(`greetingNoName.${dayPart(data.hour)}`)}
          </h1>
        </div>
        <SyncFreshness at={syncedAt} now={data.now} />
      </header>
      <PlannedWorkout program={data.program} workouts={data.workouts} today={data.today} />
      <WeekGlance week={data.week} />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <FoodToday food={data.food} />
        <LatestActivity latest={data.latest} strava={data.strava} />
      </div>
    </div>
  );
}

/** How fresh the synced data is (rendered on the server, so "ago" matches the moment of the page). */
export function SyncFreshness({ at, now }: { at: string | null; now: Date }) {
  const t = useTranslations("today.sync");
  const format = useFormatter();
  const stale = at ? now.getTime() - Date.parse(at) > STALE_MS : true;
  return (
    <p className="inline-flex items-center gap-2 text-xs text-muted" data-testid="sync-freshness">
      <span aria-hidden className={cn("size-2 rounded-full", at ? (stale ? "bg-warn" : "bg-ok") : "bg-surface-3")} />
      {at ? (
        <time dateTime={at}>{t("synced", { ago: format.relativeTime(new Date(at), now) })}</time>
      ) : (
        <span>{t("never")}</span>
      )}
    </p>
  );
}
