import { ArrowRight, Link2, MapPin, UtensilsCrossed } from "lucide-react";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import type { ReactNode } from "react";

import { buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ProgressRing } from "@/components/ui/progress-ring";
import { Empty, Failure } from "@/components/ui/states";
import { StatGrid } from "@/features/progress/components/block";
import { StatCard } from "@/features/progress/components/stat-card";
import { formatDuration, formatNumber, km } from "@/features/progress/format";
import type { ProgressSummary } from "@/features/progress/types";
import { BETTER } from "@/features/progress/types";
import type { DaySummary } from "@/features/nutrition/types";
import type { StravaConnection } from "@/features/settings/types";
import type { Loaded } from "@/lib/api";
import { sportLabel } from "@/lib/format";
import type { ActivityPage } from "@/lib/types";

const KM_DIGITS = 1;
const RING_PX = 128;

function BlockTitle({ id, children, href, linkText }: { id: string; children: ReactNode; href?: string; linkText?: string }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 id={id} className="text-label font-semibold uppercase tracking-[0.08em] text-muted">
        {children}
      </h2>
      {href && linkText ? (
        <Link href={href} className="inline-flex h-touch items-center gap-1 text-sm font-semibold text-accent-ink hover:underline">
          {linkText}
          <ArrowRight aria-hidden className="size-4" />
        </Link>
      ) : null}
    </div>
  );
}

/** This week so far against the same days of last week (`/v1/stats/summary?period=week`). */
export function WeekGlance({ week }: { week: Loaded<ProgressSummary> }) {
  const t = useTranslations("today.week");
  if (!week.ok) return <Failure title={t("failed")} message={week.error} />;
  const s = week.data;
  return (
    <Card aria-labelledby="week-title" data-testid="today-week">
      <BlockTitle id="week-title" href="/progress?period=week" linkText={t("more")}>
        {t("title")}
      </BlockTitle>
      <StatGrid>
        <StatCard label={t("distance")} value={km(s.endurance.totals.distance_m.value ?? 0)} digits={KM_DIGITS} unit={t("km")} change={s.endurance.totals.distance_m} better={BETTER.distance} period="week" />
        <StatCard label={t("workouts")} value={s.strength.sessions.value} change={s.strength.sessions} better={BETTER.sessions} period="week" />
        <StatCard label={t("activeDays")} value={s.consistency.active_days.value} change={s.consistency.active_days} better={BETTER.activeDays} period="week" />
        <StatCard
          label={t("streak")}
          value={s.consistency.training_streak_weeks}
          unit={t("weeks", { count: s.consistency.training_streak_weeks })}
          period="week"
        />
      </StatGrid>
    </Card>
  );
}

/** Today's food against the kcal target: a ring, the numbers, neutral words (P6.7). */
export function FoodToday({ food }: { food: Loaded<DaySummary> }) {
  const t = useTranslations("today.food");
  const locale = useLocale();
  if (!food.ok) return <Failure title={t("failed")} message={food.error} />;
  const f = food.data;
  const kcal = (value: number) => formatNumber(locale, value);
  if (f.entry_count === 0) {
    return (
      <Empty
        title={t("empty")}
        action={
          <Link href="/nutrition" className={buttonVariants({ variant: "secondary" })}>
            <UtensilsCrossed aria-hidden />
            {t("log")}
          </Link>
        }
      >
        {f.kcal_target != null ? t("target", { value: kcal(f.kcal_target) }) : null}
      </Empty>
    );
  }
  const target = f.kcal_target;
  const left = f.kcal_remaining;
  return (
    <Card aria-labelledby="food-title" data-testid="today-food">
      <BlockTitle id="food-title" href="/nutrition" linkText={t("open")}>
        {t("title")}
      </BlockTitle>
      <div className="flex items-center gap-5">
        {target ? (
          <ProgressRing value={f.intake_kcal / target} size={RING_PX} label={t("ringLabel", { value: kcal(f.intake_kcal), target: kcal(target) })}>
            <span className="block text-2xl font-black tabular">{kcal(f.intake_kcal)}</span>
            <span className="block text-xs text-muted">{t("of", { value: kcal(target) })}</span>
          </ProgressRing>
        ) : (
          <p className="text-hero font-black tabular">{kcal(f.intake_kcal)}</p>
        )}
        <div className="min-w-0 text-sm">
          <p className="font-semibold">
            {left == null ? t("noTarget") : left >= 0 ? t("left", { value: kcal(left) }) : t("above", { value: kcal(-left) })}
          </p>
          <p className="mt-1 text-muted tabular">
            {t("macros", { protein: kcal(f.protein_g), carbs: kcal(f.carbs_g), fat: kcal(f.fat_g) })}
          </p>
          <p className="mt-1 text-xs text-muted">{t("entries", { count: f.entry_count })}</p>
        </div>
      </div>
    </Card>
  );
}

/** The newest synced activity, or how to get one (connect Strava, or wait for the first sync). */
export function LatestActivity({ latest, strava }: { latest: Loaded<ActivityPage>; strava: Loaded<StravaConnection> }) {
  const t = useTranslations("today.activity");
  const format = useFormatter();
  const locale = useLocale();
  if (!latest.ok) return <Failure title={t("failed")} message={latest.error} />;
  const activity = latest.data.items[0];
  if (!activity) {
    const connected = strava.ok && strava.data.connected;
    return (
      <Empty
        title={connected ? t("waiting") : t("noStrava")}
        action={
          connected ? (
            <Link href="/sync" className={buttonVariants({ variant: "secondary" })}>
              {t("sync")}
            </Link>
          ) : (
            <Link href="/me/connections" className={buttonVariants({ variant: "primary" })}>
              <Link2 aria-hidden />
              {t("connect")}
            </Link>
          )
        }
      >
        {connected ? t("waitingHint") : t("noStravaHint")}
      </Empty>
    );
  }
  return (
    <Card aria-labelledby="activity-title" data-testid="today-activity">
      <BlockTitle id="activity-title" href="/activities" linkText={t("all")}>
        {t("title")}
      </BlockTitle>
      <Link href={`/activities/${activity.id}`} className="group flex items-center gap-4 rounded-control focus-visible:outline-2 focus-visible:outline-accent">
        <span aria-hidden className="grid size-12 shrink-0 place-items-center rounded-control bg-surface-2 text-accent-ink">
          <MapPin className="size-5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-lg font-bold group-hover:text-accent-ink">{activity.name}</span>
          <span className="block text-sm text-muted">
            {sportLabel(activity.sport_type)} · {format.dateTime(new Date(activity.start_date), { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
          </span>
        </span>
        <span className="shrink-0 text-right tabular">
          <span className="block text-xl font-black">{t("km", { value: formatNumber(locale, km(activity.distance_m), KM_DIGITS) })}</span>
          <span className="block text-xs text-muted">{formatDuration(activity.moving_time_s)}</span>
        </span>
      </Link>
    </Card>
  );
}
