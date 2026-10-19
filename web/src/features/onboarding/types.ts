import type { components } from "@/lib/api-types";

type Schemas = components["schemas"];

export type Settings = Schemas["SettingsOut"];
export type SettingsPatch = Schemas["SettingsPatch"];
export type MePatch = Schemas["MePatch"];
export type Tone = Settings["tone"];
export type Intensity = Settings["intensity"];
export type Profanity = Settings["profanity"];
export type Lang = Settings["lang"];
export type CoachPreview = Schemas["CoachPreviewOut"];
export type StravaConnection = Schemas["StravaConnection"];
export type LinkStatus = Schemas["LinkStatus"];
export type LinkCode = Schemas["LinkCode"];

/** How the Strava OAuth round trip ended (the API's callback adds `connected=1` or `connect_error`). */
export type StravaReturn = { connected: true } | { error: string } | null;

/** What the onboarding page knows when it renders; null where the API could not answer. */
export interface OnboardingData {
  timezone: string | null;
  settings: Pick<Settings, "lang" | "tone" | "intensity" | "profanity"> | null;
  strava: StravaConnection | null;
  telegram: LinkStatus | null;
  profile: Schemas["ProfileOut"] | null;
  stravaReturn: StravaReturn;
}
