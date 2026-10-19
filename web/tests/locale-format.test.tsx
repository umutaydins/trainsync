import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useActivityFormat } from "@/features/activities/use-activity-format";
import { effortUnit, formatEffort } from "@/features/progress/format";
import { durationParts } from "@/lib/format";
import { useDuration } from "@/lib/use-duration";
import { activity } from "./support/fixtures";
import { renderWithIntl } from "./support/intl";

const H = 3600;
const M = 60;

describe("pace from an average speed in m/s (known values)", () => {
  it.each([
    // 1500 m in 30:00
    ["swim", 1500 / (30 * M), "2:00", "per100m"],
    // 10 km in 50:00
    ["run", 10_000 / (50 * M), "5:00", "perKm"],
    // 5 km in 1:00:00
    ["walk", 5000 / H, "12:00", "perKm"],
    // 30 km in 1:00:00
    ["ride", 30_000 / H, "30", "kmh"],
  ] as const)("%s", (group, speed, shown, unit) => {
    expect(formatEffort("en", group, speed)).toBe(shown);
    expect(effortUnit(group)).toBe(unit);
  });

  it("a swim summed over activities: 5.7 km in 1:54:00 is 2:00 /100 m", () => {
    expect(formatEffort("en", "swim", 5700 / (114 * M))).toBe("2:00");
  });

  it("an activity's swim pace from its distance and time", () => {
    function Swim() {
      const fmt = useActivityFormat();
      return <p>{fmt.effort(activity(1, { sport_type: "Swim", distance_m: 1500, moving_time_s: 30 * M }))}</p>;
    }
    renderWithIntl(<Swim />);
    expect(screen.getByText("2:00 /100 m")).toBeInTheDocument();
  });
});

function Durations({ seconds }: { seconds: readonly number[] }) {
  const duration = useDuration();
  return (
    <ul>
      {seconds.map((s) => (
        <li key={s}>{duration(s)}</li>
      ))}
    </ul>
  );
}

function items(): string[] {
  return screen.getAllByRole("listitem").map((li) => li.textContent ?? "");
}

describe("durations by locale, never `25:24 h`", () => {
  const seconds = [25 * H + 24 * M + 59, 45 * M, 2 * H, 0] as const;

  it("English", () => {
    renderWithIntl(<Durations seconds={seconds} />);
    expect(items()).toEqual(["25h 24m", "45m", "2h", "0m"]);
  });

  it("Turkish", () => {
    renderWithIntl(<Durations seconds={seconds} />, "tr");
    expect(items()).toEqual(["25 sa 24 dk", "45 dk", "2 sa", "0 dk"]);
  });

  it("drops seconds and never goes negative", () => {
    expect(durationParts(3659)).toEqual({ hours: 1, minutes: 0 });
    expect(durationParts(-5)).toEqual({ hours: 0, minutes: 0 });
  });
});

describe("dates and times in the user's language and zone", () => {
  function When() {
    const fmt = useActivityFormat();
    return <p data-testid="when">{fmt.dateTime("2026-10-01T22:30:00Z")}</p>;
  }

  it("Turkish: 24-hour clock, Istanbul time (the next day there)", () => {
    renderWithIntl(<When />, "tr", "Europe/Istanbul");
    const text = screen.getByTestId("when").textContent ?? "";
    expect(text).toContain("2 Eki 2026");
    expect(text).toContain("01:30");
    expect(text).not.toMatch(/AM|PM|ÖÖ|ÖS/);
  });

  it("English in New York", () => {
    renderWithIntl(<When />, "en", "America/New_York");
    expect(screen.getByTestId("when")).toHaveTextContent("Oct 1, 2026, 6:30 PM");
  });
});
