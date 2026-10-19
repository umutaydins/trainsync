import "server-only";

import { cookies } from "next/headers";

import type { LinkStatus, SessionList, Settings, StravaConnection } from "@/features/settings/types";
import { getJson } from "@/lib/api";
import { DEFAULT_THEME, THEME_COOKIE, type Theme, isTheme } from "@/lib/theme";

/** Reads of Me's pages as the signed-in user (wrap in `load()` for the error states). */
export const settingsApi = {
  settings: () => getJson<Settings>("/v1/me/settings"),
  sessions: () => getJson<SessionList>("/v1/me/sessions"),
  strava: () => getJson<StravaConnection>("/v1/me/strava"),
  telegram: () => getJson<LinkStatus>("/v1/me/telegram"),
};

/** The theme the page was rendered with (the `theme` cookie, ADR 0039). */
export async function currentTheme(): Promise<Theme> {
  const value = (await cookies()).get(THEME_COOKIE)?.value;
  return isTheme(value) ? value : DEFAULT_THEME;
}
