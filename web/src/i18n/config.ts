/** Languages of the web app (ADR 0039): the user's `lang` setting, else the browser's, else English. */

export const LOCALES = ["en", "tr"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";

/** Cookies the BFF sets from the signed-in user's settings, so every render knows them. */
export const LOCALE_COOKIE = "lang";
export const TIME_ZONE_COOKIE = "tz";
export const DEFAULT_TIME_ZONE = "UTC";
const PREFERENCE_MAX_AGE_S = 365 * 24 * 60 * 60;
export const PREFERENCE_COOKIE_OPTIONS = {
  path: "/",
  sameSite: "lax",
  maxAge: PREFERENCE_MAX_AGE_S,
} as const;

export function isLocale(value: string | undefined | null): value is Locale {
  return value != null && (LOCALES as readonly string[]).includes(value);
}

/** The first supported language of an `Accept-Language` header, in its order of preference. */
export function negotiate(acceptLanguage: string | null | undefined): Locale {
  const ranked = (acceptLanguage ?? "")
    .split(",")
    .map((part) => {
      const [tag = "", ...params] = part.trim().split(";");
      const q = params.find((p) => p.trim().startsWith("q="));
      return { lang: tag.toLowerCase().split("-")[0], q: q ? Number(q.split("=")[1]) : 1 };
    })
    .filter((entry) => entry.lang && Number.isFinite(entry.q))
    .sort((a, b) => b.q - a.q);
  return ranked.map((entry) => entry.lang).find(isLocale) ?? DEFAULT_LOCALE;
}

export function isTimeZone(value: string | undefined | null): value is string {
  if (!value) return false;
  try {
    new Intl.DateTimeFormat("en", { timeZone: value });
    return true;
  } catch {
    return false;
  }
}
