import { render, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { AddFood } from "@/features/nutrition/components/add-food";
import { MealList } from "@/features/nutrition/components/meal-list";
import { ProfileForm } from "@/features/nutrition/components/profile-form";
import { DailyRings, EnergyBalanceCard, WeeklyAverages } from "@/features/nutrition/components/summary-cards";
import { BodyWeightChart } from "@/features/training/components/progress-charts";
import { BodyBlock, NutritionBlock } from "@/features/progress/components/habit-blocks";
import { KcalChart } from "@/features/progress/components/kcal-chart";
import { WeightChart } from "@/features/progress/components/weight-chart";
import { FoodToday } from "@/features/today/components/today-blocks";
import { renderWithIntl } from "./support/intl";
import { progressSummary, series, weightSeries } from "./support/progress-fixtures";
import { ESTIMATE_GAP_TEXT } from "@/features/nutrition/types";
import { CHICKEN, NO_PROFILE, OATS, UNKNOWN_EXERCISE, daySummary, entry, profile, weekly } from "./support/nutrition-fixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/nutrition" }));

/**
 * Nutrition screens state numbers, never verdicts (P6.7). Judgement words about food or eating,
 * and words about bodies, must not appear in anything a person can read or hear.
 */
const BLOCKLIST = [
  // verdicts on food and eating
  "good", "bad", "better", "worse", "best", "worst", "healthy", "unhealthy", "clean", "dirty", "junk",
  "cheat", "cheating", "guilt", "guilty", "sin", "sinful", "naughty", "indulge", "indulgence", "treat",
  "binge", "overeat", "overeating", "overate", "excess", "excessive", "too much", "too many", "too little",
  "over limit", "exceeded", "blew", "ruined", "failed", "failure", "warning", "danger", "careful",
  "should", "must", "allowed", "forbidden", "earn", "burn off", "work off", "make up for", "punish",
  "deserve", "willpower", "discipline", "lazy", "slip", "slipped", "on track", "off track",
  // body and weight shaming
  "fat loss", "obese", "obesity", "overweight", "underweight", "skinny", "chubby", "flabby", "bulky",
  "ugly", "beach body", "bikini", "slim down", "get rid of", "problem area", "love handles", "fatty",
];

const PATTERN = new RegExp(`\\b(${BLOCKLIST.map((w) => w.replace(/ /g, "\\s+")).join("|")})\\b`, "i");

/** Everything readable: text, plus labels, placeholders, titles and alt texts. */
function visibleStrings(container: HTMLElement): string[] {
  const strings = [container.textContent ?? ""];
  for (const el of container.querySelectorAll("*")) {
    for (const attr of ["aria-label", "placeholder", "title", "alt", "aria-description"]) {
      const value = el.getAttribute(attr);
      if (value) strings.push(value);
    }
    if (el instanceof HTMLOptionElement) strings.push(el.text);
  }
  return strings;
}

function judgementWords(ui: ReactElement): string[] {
  const { container, unmount } = render(<main>{ui}</main>);
  const found = visibleStrings(container).flatMap((s) => s.match(new RegExp(PATTERN, "gi")) ?? []);
  unmount();
  return found;
}

const TARGET_NOTE =
  "kcal_target (1500 kcal) is below the estimated basal metabolic rate (1755.5 kcal). It was saved as entered; the BMR is an estimate.";

describe("neutral nutrition copy", () => {
  it("the scanner catches judgement words", () => {
    expect(judgementWords(<p>That was a cheat day, too much sugar</p>)).toEqual(["cheat", "too much"]);
    expect(judgementWords(<input aria-label="Overweight" readOnly />)).toEqual(["Overweight"]);
    expect(judgementWords(<p>Fat 5 g · protein 30 g</p>)).toEqual([]);
  });

  it.each<[string, ReactElement]>([
    ["totals", <DailyRings key="r" summary={daySummary()} />],
    ["totals above target, incomplete macros", <DailyRings key="r2" summary={daySummary({ intake_kcal: 3100, kcal_remaining: -700, macros_complete: false })} />],
    ["totals without targets", <DailyRings key="r3" summary={daySummary(NO_PROFILE)} />],
    ["energy balance", <EnergyBalanceCard key="e" summary={daySummary()} />],
    ["energy balance, surplus", <EnergyBalanceCard key="e2" summary={daySummary({ balance_kcal: 900 })} />],
    ["energy balance, unknown exercise", <EnergyBalanceCard key="e3" summary={daySummary(UNKNOWN_EXERCISE)} />],
    ["energy balance, no profile", <EnergyBalanceCard key="e4" summary={daySummary(NO_PROFILE)} />],
    ["energy balance, no weight", <EnergyBalanceCard key="e5" summary={daySummary({ ...NO_PROFILE, estimate_unavailable_reason: "no_body_weight" })} />],
    ["week", <WeeklyAverages key="w" weekly={weekly()} />],
    ["meals", <MealList key="m" entries={[entry(), entry({ client_id: "x", meal: "snack", protein_g: null })]} />],
    ["meals, empty", <MealList key="m2" entries={[]} />],
    ["add food", <AddFood key="a" date="2026-10-18" favorites={[OATS]} recent={[CHICKEN]} />],
    ["profile", <ProfileForm key="p" profile={profile()} date="2026-10-18" />],
    ["profile with the below-BMR note", <ProfileForm key="p2" profile={profile({ warning: TARGET_NOTE })} date="2026-10-18" />],
    ["profile, new", <ProfileForm key="p3" profile={null} date="2026-10-18" />],
    ["body weight", <BodyWeightChart key="bw" items={[{ date: "2026-10-17", weight_kg: 78.4 }]} />],
  ])("%s has no judgement words", (_name, ui) => {
    expect(judgementWords(ui)).toEqual([]);
  });

  it("the add-food flow's later states too (selected food, new-food form)", async () => {
    const user = userEvent.setup();
    const { container } = render(<AddFood date="2026-10-18" favorites={[OATS]} recent={[]} />);
    await user.click(within(container).getByRole("button", { name: /Rolled oats/ }));
    await user.click(within(container).getByRole("button", { name: "Create a food" }));
    expect(within(container).getByRole("form", { name: "New food" })).toBeInTheDocument();
    expect(within(container).getByLabelText("Grams")).toBeInTheDocument();
    const words = visibleStrings(container).flatMap((s) => s.match(new RegExp(PATTERN, "gi")) ?? []);
    expect(words).toEqual([]);
  });

  it("every estimate-gap text is neutral", () => {
    for (const text of Object.values(ESTIMATE_GAP_TEXT)) expect(text).not.toMatch(PATTERN);
  });
});

describe("neutral copy on Progress and Today (P8.15)", () => {
  const s = progressSummary();
  it.each<[string, ReactElement]>([
    ["progress food", <NutritionBlock key="n" nutrition={s.nutrition} period="month" />],
    ["progress body", <BodyBlock key="b" body={s.body} period="month" />],
    ["kcal chart", <KcalChart key="k" series={series("kcal", [3100, 0, 1200], { target: 2400 })} />],
    ["weight chart", <WeightChart key="w" series={weightSeries()} />],
    ["today's food", <FoodToday key="f" food={{ ok: true, data: daySummary({ intake_kcal: 3100, kcal_remaining: -700 }) }} />],
    ["today's food, empty", <FoodToday key="f2" food={{ ok: true, data: daySummary({ entry_count: 0 }) }} />],
  ])("%s has no judgement words", (_name, ui) => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("reduce"), addEventListener: () => undefined, removeEventListener: () => undefined }));
    const { container, unmount } = renderWithIntl(<main>{ui}</main>);
    const found = visibleStrings(container).flatMap((text) => text.match(new RegExp(PATTERN, "gi")) ?? []);
    unmount();
    expect(found).toEqual([]);
  });
});
