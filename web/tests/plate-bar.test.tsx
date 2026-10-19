import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PlateBar } from "@/features/training/components/plate-bar";
import { plateLook } from "@/features/training/plates";
import { renderWithIntl as render } from "./support/intl";
import { PLATES_100, PLATES_MIXED } from "./support/training-fixtures";

function drawn(side: "left" | "right") {
  return [...document.querySelectorAll(`rect[data-side="${side}"]`)].map((r) => ({
    kg: Number(r.getAttribute("data-plate")),
    color: r.getAttribute("fill"),
    x: Number(r.getAttribute("x")),
  }));
}

describe("plate drawing", () => {
  it.each([
    ["101 kg (not exact)", PLATES_100],
    ["87.5 kg (mixed plates)", PLATES_MIXED],
  ])("draws exactly the API's plates per side: %s", (_name, answer) => {
    render(<PlateBar answer={answer} />);
    const left = drawn("left");
    const right = drawn("right");
    // The same plates on both sides, heaviest next to the collar, in the API's order.
    expect(left.map((p) => p.kg)).toEqual(answer.per_side);
    expect(right.map((p) => p.kg)).toEqual(answer.per_side);
    expect(left.map((p) => p.color)).toEqual(answer.per_side.map((kg) => plateLook(kg).color));
    // Left side grows outwards (x decreasing), right side outwards (x increasing).
    expect(left.map((p) => p.x)).toEqual([...left.map((p) => p.x)].sort((a, b) => b - a));
    expect(right.map((p) => p.x)).toEqual([...right.map((p) => p.x)].sort((a, b) => a - b));
    expect(screen.getByTestId("plates-per-side")).toHaveTextContent(answer.per_side.join(" + "));
    expect(screen.getByTestId("plate-bar")).toHaveAttribute("data-per-side", answer.per_side.join(","));
  });

  it("uses IWF colours", () => {
    expect([25, 20, 15, 10, 5, 2.5, 1.25].map((kg) => plateLook(kg).name)).toEqual([
      "red",
      "blue",
      "yellow",
      "green",
      "white",
      "black",
      "silver",
    ]);
  });

  it("says when the target cannot be made exactly", () => {
    render(<PlateBar answer={PLATES_100} />);
    expect(screen.getByText(/loaded 100 kg/)).toHaveTextContent("1 kg under the 101 kg target");
    expect(screen.getByRole("img")).toHaveAccessibleName("Bar 20 kg with 25 + 15 kg on each side");
  });

  it("draws an empty bar", () => {
    render(<PlateBar answer={{ target_kg: 20, bar_kg: 20, per_side: [], achieved_kg: 20, difference_kg: 0, exact: true }} />);
    expect(drawn("left")).toEqual([]);
    expect(screen.getByTestId("plates-per-side")).toHaveTextContent("none (empty bar)");
  });
});
