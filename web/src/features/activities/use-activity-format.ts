import { useFormatter, useTranslations } from "next-intl";

import { formatClock, paceKind } from "@/lib/format";
import type { Activity } from "@/lib/types";

const METERS_PER_KM = 1000;
const SWIM_PACE_M = 100;
const SECONDS_PER_HOUR = 3600;
const SECONDS_PER_MINUTE = 60;
const KM_DIGITS = 2;
const SPEED_DIGITS = 1;
export const NO_VALUE = "—";

/** `TrailRun` → `Trail Run`: a Strava sport type without a translation of its own. */
export function humanizeSport(sportType: string): string {
  return sportType.replace(/([a-z])([A-Z])/g, "$1 $2");
}

/** `m:ss`, rounding to whole seconds (5:59.6 → 6:00). */
function pace(seconds: number): string {
  const total = Math.round(seconds);
  return `${Math.floor(total / SECONDS_PER_MINUTE)}:${String(total % SECONDS_PER_MINUTE).padStart(2, "0")}`;
}

/** Distances, times, pace or speed, heart rate, sport names and dates in the user's language and zone. */
export function useActivityFormat() {
  const format = useFormatter();
  const units = useTranslations("common.units");
  const sports = useTranslations("activities.sports");
  const fixed = (value: number, digits: number) => format.number(value, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  const km = (meters: number, digits = KM_DIGITS) => units("km", { value: fixed(meters / METERS_PER_KM, digits) });
  const meters = (value: number) => units("m", { value: format.number(Math.round(value)) });
  const heartrate = (bpm: number | null | undefined) => (bpm == null ? NO_VALUE : units("bpm", { value: format.number(Math.round(bpm)) }));
  /** Per sport: running and on foot → min/km, swimming → min/100 m, the rest → km/h. */
  const effort = (a: Pick<Activity, "sport_type" | "distance_m" | "moving_time_s">) => {
    if (!(a.distance_m > 0) || !(a.moving_time_s > 0)) return NO_VALUE;
    switch (paceKind(a.sport_type)) {
      case "pace":
        return units("perKm", { value: pace(a.moving_time_s / (a.distance_m / METERS_PER_KM)) });
      case "swim-pace":
        return units("per100m", { value: pace(a.moving_time_s / (a.distance_m / SWIM_PACE_M)) });
      case "speed":
        return units("kmh", { value: fixed(a.distance_m / METERS_PER_KM / (a.moving_time_s / SECONDS_PER_HOUR), SPEED_DIGITS) });
    }
  };
  const sport = (type: string) => (sports.has(type) ? sports(type) : humanizeSport(type));
  const dateTime = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "medium", timeStyle: "short" });
  return { km, meters, clock: formatClock, heartrate, effort, sport, dateTime, count: (n: number) => format.number(n) };
}
