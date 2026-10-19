import { render, type RenderResult } from "@testing-library/react";
import { NextIntlClientProvider, createTranslator } from "next-intl";
import type { ReactElement, ReactNode } from "react";

import type { Locale } from "@/i18n/config";
import { NAMESPACES } from "@/i18n/messages";
import enCommon from "@/i18n/messages/en/common.json";
import enNav from "@/i18n/messages/en/nav.json";
import trCommon from "@/i18n/messages/tr/common.json";
import trNav from "@/i18n/messages/tr/nav.json";
import enAuth from "@/i18n/messages/en/auth.json";
import enLegal from "@/i18n/messages/en/legal.json";
import enOnboarding from "@/i18n/messages/en/onboarding.json";
import trAuth from "@/i18n/messages/tr/auth.json";
import trLegal from "@/i18n/messages/tr/legal.json";
import trOnboarding from "@/i18n/messages/tr/onboarding.json";
import enSettings from "@/i18n/messages/en/settings.json";
import trSettings from "@/i18n/messages/tr/settings.json";
import enAdmin from "@/i18n/messages/en/admin.json";
import trAdmin from "@/i18n/messages/tr/admin.json";
import enProgress from "@/i18n/messages/en/progress.json";
import trProgress from "@/i18n/messages/tr/progress.json";
import enToday from "@/i18n/messages/en/today.json";
import trToday from "@/i18n/messages/tr/today.json";
import enTraining from "@/i18n/messages/en/training.json";
import trTraining from "@/i18n/messages/tr/training.json";
import enWorkout from "@/i18n/messages/en/workout.json";
import trWorkout from "@/i18n/messages/tr/workout.json";
import enCheckins from "@/i18n/messages/en/checkins.json";
import trCheckins from "@/i18n/messages/tr/checkins.json";
import enNutrition from "@/i18n/messages/en/nutrition.json";
import trNutrition from "@/i18n/messages/tr/nutrition.json";
import enActivities from "@/i18n/messages/en/activities.json";
import trActivities from "@/i18n/messages/tr/activities.json";
import enSync from "@/i18n/messages/en/sync.json";
import trSync from "@/i18n/messages/tr/sync.json";

/** Every message file, synchronously (tests do not go through next-intl's request config). */
export const MESSAGES = {
  en: { common: enCommon, nav: enNav, auth: enAuth, onboarding: enOnboarding, legal: enLegal, settings: enSettings, admin: enAdmin, progress: enProgress, today: enToday, training: enTraining, workout: enWorkout, checkins: enCheckins, nutrition: enNutrition, activities: enActivities, sync: enSync },
  tr: { common: trCommon, nav: trNav, auth: trAuth, onboarding: trOnboarding, legal: trLegal, settings: trSettings, admin: trAdmin, progress: trProgress, today: trToday, training: trTraining, workout: trWorkout, checkins: trCheckins, nutrition: trNutrition, activities: trActivities, sync: trSync },
} satisfies Record<Locale, Record<(typeof NAMESPACES)[number], unknown>>;

/** `render` inside the intl provider; `rerender` keeps it (the provider is the wrapper). */
export function renderWithIntl(ui: ReactElement, locale: Locale = "en", timeZone = "UTC"): RenderResult {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]} timeZone={timeZone}>
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
