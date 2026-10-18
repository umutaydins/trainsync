import { describe, expect, it } from "vitest";

import { parseActivityFilters, toApiQuery } from "@/lib/activities-query";

describe("activity filters", () => {
  it("keeps valid filters and drops junk", () => {
    expect(parseActivityFilters({ from: "2026-01-01", to: "nope", sport_type: "Run" })).toEqual({
      from: "2026-01-01",
      to: undefined,
      sport_type: "Run",
    });
    expect(parseActivityFilters({ from: "", sport_type: "" })).toEqual({ from: undefined, to: undefined, sport_type: undefined });
  });

  it("makes the inclusive `to` day exclusive for the API", () => {
    expect(toApiQuery({ from: "2026-01-01", to: "2026-12-31", sport_type: "Ride" })).toEqual({
      limit: "50",
      from: "2026-01-01",
      to: "2027-01-01",
      sport_type: "Ride",
    });
    expect(toApiQuery({})).toEqual({ limit: "50" });
  });
});
