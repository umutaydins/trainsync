import { describe, expect, it } from "vitest";

import { passwordErrors } from "@/features/settings/components/password-form";
import { profilePatch } from "@/features/settings/components/profile-form";
import { countries } from "@/features/settings/countries";
import { deviceName } from "@/features/settings/devices";
import {
  changedFields,
  confirmMatches,
  formatQuietHours,
  parseQuietHours,
  resetPatch,
  sugarLimit,
  toTimeInput,
  wholeNumber,
} from "@/features/settings/settings-form";
import { settings } from "./support/settings-fixtures";

describe("settings helpers (P8.14)", () => {
  it("sends only the fields that changed, comparing times without seconds", () => {
    const current = settings();
    expect(
      changedFields(current, { checkin_time: "21:00", quiet_hours: "23:00-07:00", checkin_reminder_minutes: 30 }),
    ).toEqual({ checkin_reminder_minutes: 30 });
    expect(changedFields(current, { country: null })).toEqual({});
    expect(changedFields(current, { tone: "hardcore", intensity: "normal" })).toEqual({ tone: "hardcore" });
  });

  it("resets a field with null", () => {
    expect(resetPatch("sugar_limit_g")).toEqual({ sugar_limit_g: null });
  });

  it("reads and writes times and quiet hours", () => {
    expect(toTimeInput("06:30:00")).toBe("06:30");
    expect(parseQuietHours("22:30-06:30")).toEqual({ start: "22:30", end: "06:30" });
    expect(formatQuietHours("22:30", "06:30")).toBe("22:30-06:30");
  });

  it("checks numbers against the API's bounds", () => {
    expect(wholeNumber("90", { min: 0, max: 720 })).toBe(90);
    expect(wholeNumber("721", { min: 0, max: 720 })).toBeNull();
    expect(wholeNumber("1.5", { min: 0, max: 720 })).toBeNull();
    expect(wholeNumber("", { min: 0, max: 720 })).toBeNull();
    expect(sugarLimit("37,5")).toBe(37.5);
    expect(sugarLimit("0")).toBeNull();
    expect(sugarLimit("1001")).toBeNull();
  });

  it("matches the typed confirmation word in the user's language", () => {
    expect(confirmMatches(" delete ", "DELETE", "en")).toBe(true);
    expect(confirmMatches("sil", "SİL", "tr")).toBe(true);
    expect(confirmMatches("SIL", "SİL", "tr")).toBe(false);
    expect(confirmMatches("DELET", "DELETE", "en")).toBe(false);
  });

  it("names devices from their user agent", () => {
    expect(deviceName("Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit Version/26.0 Mobile Safari/604.1")).toBe(
      "Safari · iPhone",
    );
    expect(deviceName("Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/140.0 Safari/537.36 Edg/140.0")).toBe("Edge · Windows");
    expect(deviceName("Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko Firefox/140.0")).toBe("Firefox · Linux");
    expect(deviceName("curl/8.0")).toBeNull();
    expect(deviceName(null)).toBeNull();
  });

  it("validates the profile and sends only what changed", () => {
    const me = { display_name: "Runner", timezone: "Europe/Berlin" };
    expect(profilePatch(me, " Runner ", "Europe/Berlin")).toEqual({});
    expect(profilePatch(me, "Umut", "Europe/Istanbul")).toEqual({ display_name: "Umut", timezone: "Europe/Istanbul" });
    expect(profilePatch(me, "   ", "Europe/Berlin")).toBeNull();
  });

  it("checks the password form before sending", () => {
    expect(passwordErrors("", "a long enough one", "a long enough one")).toEqual({ current: "required" });
    expect(passwordErrors("old", "short", "short")).toEqual({ next: "tooShort" });
    expect(passwordErrors("old", "a long enough one", "another long one")).toEqual({ repeat: "mismatch" });
    expect(passwordErrors("old", "a long enough one", "a long enough one")).toEqual({});
  });

  it("lists countries by name in the user's language, without non-countries", () => {
    const tr = countries("tr");
    expect(tr.find((c) => c.code === "DE")?.name).toBe("Almanya");
    expect(tr.some((c) => c.code === "EU" || c.code === "UN")).toBe(false);
    expect(countries("en").find((c) => c.code === "TR")?.name).toMatch(/T(ü|u)rk/);
  });
});
