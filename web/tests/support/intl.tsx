import { render, type RenderResult } from "@testing-library/react";
import { NextIntlClientProvider, createTranslator } from "next-intl";
import type { ReactElement, ReactNode } from "react";

import type { Locale } from "@/i18n/config";
import { NAMESPACES } from "@/i18n/messages";
import enCommon from "@/i18n/messages/en/common.json";
import enNav from "@/i18n/messages/en/nav.json";
import trCommon from "@/i18n/messages/tr/common.json";
import trNav from "@/i18n/messages/tr/nav.json";

/** Every message file, synchronously (tests do not go through next-intl's request config). */
export const MESSAGES = {
  en: { common: enCommon, nav: enNav },
  tr: { common: trCommon, nav: trNav },
} satisfies Record<Locale, Record<(typeof NAMESPACES)[number], unknown>>;

/** `render` inside the intl provider; `rerender` keeps it (the provider is the wrapper). */
export function renderWithIntl(ui: ReactElement, locale: Locale = "en"): RenderResult {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]} timeZone="UTC">
        {children}
      </NextIntlClientProvider>
    );
  }
  return render(ui, { wrapper: Wrapper });
}

/** A server-side `getTranslations` stand-in for `vi.mock("next-intl/server", ...)`. */
export function translatorFor(locale: Locale = "en") {
  return async (namespace?: string) =>
    createTranslator({ locale, messages: MESSAGES[locale], namespace: namespace as never });
}
