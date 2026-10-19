import type { ProgramOut } from "@/features/training/types";

type ProgramDay = ProgramOut["days"][number];

/**
 * Which program day is planned on a weekday: the same rule as the coach's reminders
 * (`modules/coach/schedule.py`, ADR 0030). A day's own weekday (0 = Monday) wins; without one
 * it takes its slot in the default spread for the program's days per week.
 */
const DEFAULT_WEEKDAYS: Record<number, readonly number[]> = {
  1: [0],
  2: [0, 3],
  3: [0, 2, 4],
  4: [0, 1, 3, 4],
  5: [0, 1, 2, 3, 4],
  6: [0, 1, 2, 3, 4, 5],
  7: [0, 1, 2, 3, 4, 5, 6],
};
const MIN_DAYS = 1;
const MAX_DAYS = 7;
const DAYS_PER_WEEK = 7;

export function weekdayOf(day: ProgramDay, daysPerWeek: number): number {
  if (day.weekday != null) return day.weekday;
  const spread = DEFAULT_WEEKDAYS[Math.max(MIN_DAYS, Math.min(MAX_DAYS, daysPerWeek))] ?? [0];
  return spread[day.day_index % spread.length] ?? 0;
}

function byIndex(program: ProgramOut): ProgramDay[] {
  return [...program.days].sort((a, b) => a.day_index - b.day_index);
}

/** The day planned for `weekday` (0 = Monday), the first by index if several; null on a rest day. */
export function plannedOn(program: ProgramOut, weekday: number): ProgramDay | null {
  return byIndex(program).find((day) => weekdayOf(day, program.days_per_week) === weekday) ?? null;
}

/** The next planned day after `weekday` (wrapping into next week), with its weekday. */
export function nextPlanned(program: ProgramOut, weekday: number): { day: ProgramDay; weekday: number } | null {
  for (let ahead = 1; ahead <= DAYS_PER_WEEK; ahead += 1) {
    const next = (weekday + ahead) % DAYS_PER_WEEK;
    const day = plannedOn(program, next);
    if (day) return { day, weekday: next };
  }
  return null;
}

/** The weekday (0 = Monday) of a calendar day `YYYY-MM-DD`. */
export function weekdayOfDate(day: string): number {
  return (new Date(`${day}T00:00:00Z`).getUTCDay() + DAYS_PER_WEEK - 1) % DAYS_PER_WEEK;
}
