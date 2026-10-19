import { useSyncExternalStore } from "react";

/**
 * ISO 3166-1 alpha-2 countries with their names in `locale`, read in the browser only (server and
 * browser ICU data differ, like the time zones). The API takes any two capital letters; the
 * emergency number follows the country where the API knows one.
 */
const A = "A".charCodeAt(0);
const LETTERS = 26;
/** Region codes ICU names that are not countries. */
const NOT_COUNTRIES = new Set(["EU", "EZ", "UN", "QO", "XA", "XB", "XK", "ZZ"]);

export interface Country {
  code: string;
  name: string;
}

const cache = new Map<string, readonly Country[]>();
const NONE: readonly Country[] = [];

export function countries(locale: string): readonly Country[] {
  const cached = cache.get(locale);
  if (cached) return cached;
  const names = new Intl.DisplayNames([locale], { type: "region", fallback: "none" });
  const list: Country[] = [];
  for (let i = 0; i < LETTERS; i += 1) {
    for (let j = 0; j < LETTERS; j += 1) {
      const code = String.fromCharCode(A + i, A + j);
      const name = NOT_COUNTRIES.has(code) ? undefined : names.of(code);
      if (name && name !== code) list.push({ code, name });
    }
  }
  list.sort((a, b) => a.name.localeCompare(b.name, locale));
  cache.set(locale, list);
  return list;
}

const subscribe = () => () => undefined;

/** The country list; empty on the server render, filled on hydration. */
export function useCountries(locale: string): readonly Country[] {
  return useSyncExternalStore(subscribe, () => countries(locale), () => NONE);
}
