import "server-only";

import { nutritionApi } from "@/features/nutrition/api";
import type { LinkStatus, OnboardingData, Settings, StravaConnection, StravaReturn } from "@/features/onboarding/types";
import { api, getJson, load } from "@/lib/api";

/** Everything the onboarding steps start from; a step whose read failed starts from defaults. */
export async function onboardingData(stravaReturn: StravaReturn): Promise<OnboardingData> {
  const [me, settings, strava, telegram, profile] = await Promise.all([
    load(api.me),
    load(() => getJson<Settings>("/v1/me/settings")),
    load(() => getJson<StravaConnection>("/v1/me/strava")),
    load(() => getJson<LinkStatus>("/v1/me/telegram")),
    // 404 until the user has a profile.
    load(() => nutritionApi.profile()),
  ]);
  return {
    timezone: me.ok ? me.data.timezone : null,
    settings: settings.ok
      ? {
          lang: settings.data.lang,
          tone: settings.data.tone,
          intensity: settings.data.intensity,
          profanity: settings.data.profanity,
        }
      : null,
    strava: strava.ok ? strava.data : null,
    telegram: telegram.ok ? telegram.data : null,
    profile: profile.ok ? profile.data : null,
    stravaReturn,
  };
}
