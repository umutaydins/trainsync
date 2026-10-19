"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Segmented } from "@/components/ui/segmented";
import { THEMES, THEME_COOKIE, type Theme } from "@/lib/theme";
import { PREFERENCE_COOKIE_OPTIONS } from "@/i18n/config";

/** System / dark / light: switches at once and remembers the choice in a cookie. */
export function ThemeSwitch({ initial }: { initial: Theme }) {
  const [theme, setTheme] = useState(initial);
  const t = useTranslations("common.theme");
  return (
    <Segmented<Theme>
      label={t("label")}
      value={theme}
      options={THEMES.map((value) => ({ value, label: t(value) }))}
      onChange={(next) => {
        setTheme(next);
        const root = document.documentElement;
        root.classList.remove(...THEMES);
        root.classList.add(next);
        const { path, maxAge, sameSite } = PREFERENCE_COOKIE_OPTIONS;
        document.cookie = `${THEME_COOKIE}=${next}; path=${path}; max-age=${maxAge}; samesite=${sameSite}`;
      }}
    />
  );
}
