/** The colour theme (ADR 0039): a cookie, so the server renders it without a flash. */

export const THEMES = ["system", "dark", "light"] as const;
export type Theme = (typeof THEMES)[number];
export const DEFAULT_THEME: Theme = "system";
export const THEME_COOKIE = "theme";

export function isTheme(value: string | undefined | null): value is Theme {
  return value != null && (THEMES as readonly string[]).includes(value);
}

/** Browser-chrome colours per theme (the `--bg` token of each). */
export const THEME_COLORS = { dark: "#08090b", light: "#f4f5f1" } as const;
