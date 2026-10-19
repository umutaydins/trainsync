import { useSyncExternalStore } from "react";

/** IANA time zones for pickers, read in the browser only (server and browser ICU data differ). */

const FALLBACK_ZONE = "UTC";
let cachedZones: readonly string[] | null = null;
const NO_ZONES: readonly string[] = [];

export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || FALLBACK_ZONE;
}

/** Every zone the browser knows, with its own zone and UTC always among them. */
export function timeZones(): readonly string[] {
  if (cachedZones) return cachedZones;
  const known = new Set(Intl.supportedValuesOf("timeZone"));
  known.add(browserTimeZone());
  known.add(FALLBACK_ZONE);
  cachedZones = [...known].sort();
  return cachedZones;
}

const subscribe = () => () => undefined;

/** `{zone, zones}` of this browser; empty on the server render, filled on hydration. */
export function useBrowserTimeZones(): { zone: string; zones: readonly string[] } {
  const zone = useSyncExternalStore(subscribe, browserTimeZone, () => "");
  const zones = useSyncExternalStore(subscribe, timeZones, () => NO_ZONES);
  return { zone, zones };
}
