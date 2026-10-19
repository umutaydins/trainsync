import { describe, expect, it } from "vitest";

import { formatClock, paceKind } from "@/lib/format";

describe("clock", () => {
  it("shows seconds, hours only when needed", () => {
    expect(formatClock(3000)).toBe("50:00");
    expect(formatClock(3725)).toBe("1:02:05");
    expect(formatClock(59)).toBe("0:59");
    expect(formatClock(-5)).toBe("0:00");
  });
});

describe("pace or speed per sport", () => {
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
});
