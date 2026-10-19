import "server-only";

import type { NextResponse } from "next/server";

import {
  LOCALE_COOKIE,
  PREFERENCE_COOKIE_OPTIONS,
  TIME_ZONE_COOKIE,
  isLocale,
  isTimeZone,
} from "@/i18n/config";
import { upstreamGet } from "@/lib/upstream";

/**
 * The user's language (`/v1/me/settings`) and time zone (`/v1/me`) as cookies, so every render
 * speaks the user's language in their zone without asking the API first (ADR 0039).
 */
export interface Preferences {
  lang?: string;
  timezone?: string;
}

/** What an API answer tells about the user's preferences (only these two paths carry them). */
export function preferencesIn(path: string, data: unknown): Preferences {
  if (!data || typeof data !== "object") return {};
  const record = data as Record<string, unknown>;
  if (path === "/v1/me/settings" && typeof record.lang === "string") return { lang: record.lang };
  if (path === "/v1/me" && typeof record.timezone === "string") return { timezone: record.timezone };
  return {};
}

export function rememberPreferences(response: NextResponse, preferences: Preferences): void {
  if (isLocale(preferences.lang)) {
    response.cookies.set(LOCALE_COOKIE, preferences.lang, PREFERENCE_COOKIE_OPTIONS);
  }
  if (isTimeZone(preferences.timezone)) {
    response.cookies.set(TIME_ZONE_COOKIE, preferences.timezone, PREFERENCE_COOKIE_OPTIONS);
  }
}

/** Right after sign-in: read both from the API with the new token (best effort). */
export async function loadPreferences(token: string): Promise<Preferences> {
  const [settings, me] = await Promise.all([
    upstreamGet("/v1/me/settings", new URLSearchParams(), token),
    upstreamGet("/v1/me", new URLSearchParams(), token),
  ]);
  return {
    ...(settings.ok ? preferencesIn("/v1/me/settings", settings.data) : {}),
    ...(me.ok ? preferencesIn("/v1/me", me.data) : {}),
  };
}
