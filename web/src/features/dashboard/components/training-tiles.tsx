import Link from "next/link";

import { Skeleton } from "@/components/ui";
import { load } from "@/lib/api";
import { nutritionApi } from "@/features/nutrition/api";
import type { DaySummary } from "@/features/nutrition/types";
import { kcal, utcToday, weekStart } from "@/features/nutrition/types";
import { trainingApi } from "@/features/training/api";
import type { WorkoutSummary } from "@/features/training/types";
import { formatVolume } from "@/features/training/types";

/** Workouts that started in the ISO week (UTC) of `today`. */
export function gymWeek(workouts: WorkoutSummary[], today: string): { sessions: number; volumeKg: number } {
  const monday = weekStart(today);
  const inWeek = workouts.filter((w) => w.started_at.slice(0, 10) >= monday && w.started_at.slice(0, 10) <= today);
  return { sessions: inWeek.length, volumeKg: inWeek.reduce((sum, w) => sum + w.volume_kg, 0) };
}

function Tile({ label, value, hint, href, testId }: { label: string; value: string; hint: string; href: string; testId: string }) {
  return (
    <Link href={href} className="block rounded-2xl border border-border bg-surface p-4 transition hover:border-accent/50 sm:p-5" data-testid={testId}>
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight sm:text-3xl">{value}</p>
      <p className="mt-0.5 text-xs text-muted">{hint}</p>
    </Link>
  );
}

function intakeHint(summary: DaySummary): string {
  const entries = `${summary.entry_count} ${summary.entry_count === 1 ? "entry" : "entries"}`;
  return summary.kcal_target ? `${entries} · target ${kcal(summary.kcal_target)}` : entries;
}

/** "This week in the gym" and "Today's intake" (P6.7). Independent of the dashboard's range filter. */
export async function TrainingTilesBlock({ now = new Date() }: { now?: Date }) {
  const today = utcToday(now);
  const [workouts, intake] = await Promise.all([load(() => trainingApi.workouts(50)), load(() => nutritionApi.summary(today))]);
  const week = workouts.ok ? gymWeek(workouts.data.items, today) : null;
  return (
    <div className="grid grid-cols-2 gap-3" data-testid="training-tiles">
      <Tile
        testId="tile-gym"
        href="/training/history"
        label="This week in the gym"
        value={week ? `${week.sessions} ${week.sessions === 1 ? "session" : "sessions"}` : "—"}
        hint={week ? `${formatVolume(week.volumeKg)} lifted` : workouts.ok ? "" : "could not load workouts"}
      />
      <Tile
        testId="tile-intake"
        href="/nutrition"
        label="Today’s intake"
        value={intake.ok ? kcal(intake.data.intake_kcal) : "—"}
        hint={intake.ok ? intakeHint(intake.data) : "could not load the food log"}
      />
    </div>
  );
}

export function TrainingTilesSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3">
      <Skeleton className="h-[92px] rounded-2xl sm:h-[104px]" label="Loading gym and intake" />
      <Skeleton className="h-[92px] rounded-2xl sm:h-[104px]" />
    </div>
  );
}
