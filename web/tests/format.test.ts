import { describe, expect, it } from "vitest";

import {
  formatAgo,
  formatClock,
  formatDate,
  formatDateTime,
  formatDay,
  formatDuration,
  formatHeartrate,
  formatKm,
  formatMeters,
  formatPaceOrSpeed,
  paceKind,
  paceLabel,
  sportLabel,
} from "@/lib/format";

describe("distance", () => {
  it("formats km with fixed decimals", () => {
    expect(formatKm(10_012.5)).toBe("10.01 km");
    expect(formatKm(352_295, 1)).toBe("352.3 km");
    expect(formatKm(1_234_567, 1)).toBe("1,234.6 km");
    expect(formatKm(0)).toBe("0.00 km");
  });

  it("formats meters", () => {
    expect(formatMeters(2493.4)).toBe("2,493 m");
  });
});

describe("durations", () => {
  it("h:mm drops seconds", () => {
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(59)).toBe("0:00");
    expect(formatDuration(3000)).toBe("0:50");
    expect(formatDuration(3600 + 5 * 60 + 59)).toBe("1:05");
    expect(formatDuration(74_600)).toBe("20:43");
    expect(formatDuration(-5)).toBe("0:00");
  });

  it("clock shows seconds, hours only when needed", () => {
    expect(formatClock(3000)).toBe("50:00");
    expect(formatClock(3725)).toBe("1:02:05");
    expect(formatClock(59)).toBe("0:59");
  });
});

describe("pace and speed per sport", () => {
  it.each([
    ["Run", "pace"],
    ["TrailRun", "pace"],
    ["VirtualRun", "pace"],
    ["Walk", "pace"],
    ["Hike", "pace"],
    ["Swim", "swim-pace"],
    ["Ride", "speed"],
    ["VirtualRide", "speed"],
    ["GravelRide", "speed"],
    ["Rowing", "speed"],
  ] as const)("%s → %s", (sport, kind) => {
    expect(paceKind(sport)).toBe(kind);
  });

  it("running → min/km", () => {
    expect(formatPaceOrSpeed("Run", 10_000, 3000)).toBe("5:00 /km");
    expect(formatPaceOrSpeed("Run", 10_200, 3000)).toBe("4:54 /km");
    expect(formatPaceOrSpeed("Run", 5000, 1652)).toBe("5:30 /km");
    expect(formatPaceOrSpeed("TrailRun", 1000, 359.6)).toBe("6:00 /km");
  });

  it("cycling → km/h", () => {
    expect(formatPaceOrSpeed("Ride", 40_000, 3600)).toBe("40.0 km/h");
    expect(formatPaceOrSpeed("Ride", 52_300, 6300)).toBe("29.9 km/h");
  });

  it("swimming → min/100 m", () => {
    expect(formatPaceOrSpeed("Swim", 2000, 2400)).toBe("2:00 /100 m");
  });

  it("no distance or time → dash", () => {
    expect(formatPaceOrSpeed("Run", 0, 3000)).toBe("—");
    expect(formatPaceOrSpeed("Ride", 1000, 0)).toBe("—");
    expect(formatPaceOrSpeed("WeightTraining", 0, 0)).toBe("—");
  });

  it("labels", () => {
    expect(paceLabel("Run")).toBe("Avg pace");
    expect(paceLabel("Ride")).toBe("Avg speed");
  });
});

describe("other values", () => {
  it("heart rate", () => {
    expect(formatHeartrate(151.6)).toBe("152 bpm");
    expect(formatHeartrate(null)).toBe("—");
  });

  it("sport labels", () => {
    expect(sportLabel("TrailRun")).toBe("Trail Run");
    expect(sportLabel("Run")).toBe("Run");
  });
});

describe("dates", () => {
  it("uses the display time zone (Europe/Istanbul by default)", () => {
    expect(formatDateTime("2026-10-01T22:30:00Z")).toBe("2 Oct 2026, 01:30");
    expect(formatDate("2026-10-01T22:30:00Z")).toBe("2 Oct 2026");
    expect(formatDateTime("2026-10-01T22:30:00Z", "UTC")).toBe("1 Oct 2026, 22:30");
  });

  it("formats calendar days without shifting them", () => {
    expect(formatDay("2026-09-28")).toBe("28 Sep");
    expect(formatDay("2026-09-28", true)).toBe("28 Sep 2026");
  });

  it("ago", () => {
    const now = new Date("2026-10-18T12:00:00Z");
    expect(formatAgo("2026-10-18T11:59:30Z", now)).toBe("just now");
    expect(formatAgo("2026-10-18T11:55:00Z", now)).toBe("5 min ago");
    expect(formatAgo("2026-10-18T09:00:00Z", now)).toBe("3 h ago");
    expect(formatAgo("2026-10-16T09:00:00Z", now)).toBe("2 d ago");
  });
});
