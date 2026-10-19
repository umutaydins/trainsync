/** Display formatting: metric units, fixed locale, configurable display time zone. */

export const DISPLAY_TZ = process.env.NEXT_PUBLIC_TZ || "Europe/Istanbul";
const LOCALE = "en-GB";
export const NO_VALUE = "—";

const PACE_SPORTS = new Set(["Run", "TrailRun", "VirtualRun", "Walk", "Hike"]);
const SWIM_SPORTS = new Set(["Swim"]);

export function formatKm(meters: number, digits = 2): string {
  return `${(meters / 1000).toLocaleString(LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} km`;
}

export function formatMeters(meters: number): string {
  return `${Math.round(meters).toLocaleString(LOCALE)} m`;
}

/** `h:mm` (seconds are dropped, not rounded, so totals never run ahead). */
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return `${hours}:${String(minutes).padStart(2, "0")}`;
}

/** `h:mm:ss`, or `m:ss` under an hour. */
export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${secs}` : `${minutes}:${secs}`;
}

/** `m:ss` for a pace in seconds, rounding to whole seconds (5:59.6 → 6:00). */
function formatPace(secondsPerUnit: number): string {
  const total = Math.round(secondsPerUnit);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export type PaceKind = "pace" | "swim-pace" | "speed";

export function paceKind(sportType: string): PaceKind {
  if (PACE_SPORTS.has(sportType)) return "pace";
  if (SWIM_SPORTS.has(sportType)) return "swim-pace";
  return "speed";
}

/**
 * Per-sport effort figure: running and on-foot sports → min/km, swimming → min/100 m,
 * everything else (cycling, …) → km/h. Missing distance or time → "—".
 */
export function formatPaceOrSpeed(sportType: string, distanceM: number, movingTimeS: number): string {
  if (!(distanceM > 0) || !(movingTimeS > 0)) return NO_VALUE;
  switch (paceKind(sportType)) {
    case "pace":
      return `${formatPace(movingTimeS / (distanceM / 1000))} /km`;
    case "swim-pace":
      return `${formatPace(movingTimeS / (distanceM / 100))} /100 m`;
    case "speed":
      return `${((distanceM / 1000) / (movingTimeS / 3600)).toLocaleString(LOCALE, {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      })} km/h`;
  }
}

export function paceLabel(sportType: string): string {
  return paceKind(sportType) === "speed" ? "Avg speed" : "Avg pace";
}

export function formatHeartrate(bpm: number | null | undefined): string {
  return bpm == null ? NO_VALUE : `${Math.round(bpm)} bpm`;
}

export function formatCount(value: number): string {
  return value.toLocaleString(LOCALE);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Numeric parts only from Intl (time zone math); month names are ours, as ICU versions differ. */
function parts(iso: string, timeZone: string, withTime: boolean): Record<string, string> {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone,
    day: "numeric",
    month: "numeric",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit", hourCycle: "h23" } : {}),
  });
  const values = Object.fromEntries(
    formatter.formatToParts(new Date(iso)).map((p) => [p.type, p.value]),
  );
  return { ...values, month: MONTHS[Number(values.month) - 1] ?? "" };
}

// Built from parts, so server (Node ICU) and browser render the same string (no hydration diff).
export function formatDate(iso: string, timeZone = DISPLAY_TZ): string {
  const p = parts(iso, timeZone, false);
  return `${p.day} ${p.month} ${p.year}`;
}

export function formatDateTime(iso: string, timeZone = DISPLAY_TZ): string {
  const p = parts(iso, timeZone, true);
  return `${p.day} ${p.month} ${p.year}, ${p.hour}:${p.minute}`;
}

/** A calendar date (`YYYY-MM-DD`, no time zone) such as an ISO week start: `28 Sep`. */
export function formatDay(day: string, withYear = false): string {
  const p = parts(`${day}T00:00:00Z`, "UTC", false);
  return withYear ? `${p.day} ${p.month} ${p.year}` : `${p.day} ${p.month}`;
}

/** Coarse "how long ago" for freshness indicators: `just now`, `5 min ago`, `3 h ago`, `2 d ago`. */
export function formatAgo(iso: string, now: Date): string {
  const seconds = Math.max(0, (now.getTime() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86_400)} d ago`;
}

/** Splits `TrailRun` → `Trail Run` for display. */
export function sportLabel(sportType: string): string {
  return sportType.replace(/([a-z])([A-Z])/g, "$1 $2");
}
