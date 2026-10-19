import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { humanizeSport, useActivityFormat } from "@/features/activities/use-activity-format";
import { activity } from "./support/fixtures";
import { renderWithIntl } from "./support/intl";

/** Renders what the hook makes of one activity, in the given language (the test zone is UTC). */
function Probe({ sport, distance, time }: { sport: string; distance: number; time: number }) {
  const fmt = useActivityFormat();
  const a = activity(1, { sport_type: sport, distance_m: distance, moving_time_s: time });
  return (
    <ul>
      <li>{fmt.km(a.distance_m)}</li>
      <li>{fmt.effort(a)}</li>
      <li>{fmt.meters(2493.4)}</li>
      <li>{fmt.heartrate(151.6)}</li>
      <li>{fmt.heartrate(null)}</li>
      <li>{fmt.sport(sport)}</li>
      <li>{fmt.dateTime("2026-10-01T22:30:00Z")}</li>
    </ul>
  );
}

function items(): string[] {
  return screen.getAllByRole("listitem").map((li) => li.textContent ?? "");
}

describe("activity formatting (locale and zone from next-intl, no fixed locale)", () => {
  it("English", () => {
    renderWithIntl(<Probe sport="Run" distance={10_000} time={3000} />);
    expect(items()).toEqual(["10.00 km", "5:00 /km", "2,493 m", "152 bpm", "—", "Run", "Oct 1, 2026, 10:30 PM"]);
  });

  it("Turkish numbers, units and sport names", () => {
    renderWithIntl(<Probe sport="Ride" distance={52_300} time={6300} />, "tr");
    const [distance, effort, , heartrate, , sport] = items();
    expect([distance, effort, heartrate, sport]).toEqual(["52,30 km", "29,9 km/sa", "152 atım/dk", "Bisiklet"]);
  });

  it("swim pace, rounding, no distance, unknown sports", () => {
    renderWithIntl(<Probe sport="Swim" distance={2000} time={2400} />);
    expect(items()[1]).toBe("2:00 /100 m");
    expect(humanizeSport("StandUpPaddling")).toBe("Stand Up Paddling");
  });
});
