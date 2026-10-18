import { describe, expect, it } from "vitest";

import { parseRange, presetRange, rangeHref, weekStart } from "@/lib/range";

const TODAY = new Date("2026-10-18T21:00:00Z"); // a Sunday

describe("ranges", () => {
  it("weekStart is the ISO Monday", () => {
    expect(weekStart(TODAY).toISOString().slice(0, 10)).toBe("2026-10-12");
    expect(weekStart(new Date("2026-10-12T00:00:00Z")).toISOString().slice(0, 10)).toBe("2026-10-12");
  });

  it("presets cover N whole ISO weeks up to today", () => {
    expect(presetRange(4, TODAY)).toEqual({ from: "2026-09-21", to: "2026-10-18" });
    expect(presetRange(12, TODAY)).toEqual({ from: "2026-07-27", to: "2026-10-18" });
    expect(presetRange(52, TODAY).from).toBe("2025-10-20");
  });

  it("defaults to 12 weeks", () => {
    expect(parseRange({}, TODAY)).toEqual({ preset: "12w", from: "2026-07-27", to: "2026-10-18", sportType: undefined });
    expect(parseRange({ range: "bogus" }, TODAY).preset).toBe("12w");
  });

  it("reads presets, custom ranges and the sport", () => {
    expect(parseRange({ range: "4w", sport_type: "Run" }, TODAY)).toMatchObject({ preset: "4w", sportType: "Run" });
    expect(parseRange({ from: "2025-01-01", to: "2025-12-31" }, TODAY)).toMatchObject({
      preset: "custom",
      from: "2025-01-01",
      to: "2025-12-31",
    });
  });

  it("ignores invalid custom ranges", () => {
    for (const params of [
      { from: "2025-12-31", to: "2025-01-01" },
      { from: "2025-02-30", to: "2025-03-01" },
      { from: "yesterday", to: "2025-03-01" },
      { from: "2025-01-01" },
    ]) {
      expect(parseRange(params, TODAY).preset).toBe("12w");
    }
  });

  it("builds links that keep the other filters", () => {
    const range = parseRange({ range: "4w", sport_type: "Ride" }, TODAY);
    expect(rangeHref(range, { preset: "52w" })).toBe("/?range=52w&sport_type=Ride");
    expect(rangeHref(range, { preset: "12w" })).toBe("/?sport_type=Ride");
    expect(rangeHref(range, { sportType: undefined })).toBe("/?range=4w");
    expect(rangeHref(range, { preset: "custom", from: "2025-01-01", to: "2025-02-01" })).toBe(
      "/?from=2025-01-01&to=2025-02-01&sport_type=Ride",
    );
    expect(rangeHref(parseRange({}, TODAY), {})).toBe("/");
  });
});
