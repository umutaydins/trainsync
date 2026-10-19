/**
 * Locale-free number shapes shared by the screens. Everything a person reads in their language
 * (numbers, units, dates, time zones) goes through next-intl (`useFormatter`, the request's
 * `timeZone` from the user's settings): see the feature `use-*-format` hooks.
 */

const SECONDS_PER_HOUR = 3600;
const SECONDS_PER_MINUTE = 60;

const PACE_SPORTS = new Set(["Run", "TrailRun", "VirtualRun", "Walk", "Hike"]);
const SWIM_SPORTS = new Set(["Swim"]);

/** `h:mm:ss`, or `m:ss` under an hour (a stopwatch reads the same in every language). */
export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / SECONDS_PER_HOUR);
  const minutes = Math.floor((total % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE);
  const secs = String(total % SECONDS_PER_MINUTE).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${secs}` : `${minutes}:${secs}`;
}

export type PaceKind = "pace" | "swim-pace" | "speed";

/** Running and on-foot sports → min/km, swimming → min/100 m, everything else → km/h. */
export function paceKind(sportType: string): PaceKind {
  if (PACE_SPORTS.has(sportType)) return "pace";
  if (SWIM_SPORTS.has(sportType)) return "swim-pace";
  return "speed";
}
