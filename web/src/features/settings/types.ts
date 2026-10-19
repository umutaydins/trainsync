import type { components } from "@/lib/api-types";

type Schemas = components["schemas"];

export type Me = Schemas["MeOut"];
export type MePatch = Schemas["MePatch"];
export type Settings = Schemas["SettingsOut"];
export type SettingsPatch = Schemas["SettingsPatch"];
export type SettingsField = keyof SettingsPatch;
export type Lang = Settings["lang"];
export type Session = Schemas["SessionOut"];
export type SessionList = Schemas["SessionList"];
export type PasswordChange = Schemas["PasswordChangeIn"];
export type DeleteAccount = Schemas["DeleteAccountIn"];
export type StravaConnection = Schemas["StravaConnection"];
export type LinkStatus = Schemas["LinkStatus"];
