import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AddFood } from "@/features/nutrition/components/add-food";
import { MealList } from "@/features/nutrition/components/meal-list";
import { ProfileForm } from "@/features/nutrition/components/profile-form";
import { DailyRings, EnergyBalanceCard, WeeklyAverages } from "@/features/nutrition/components/summary-cards";
import { CSRF_COOKIE } from "@/lib/csrf-cookie";
import { addDays, scaled, weekStart } from "@/features/nutrition/types";
import { jsonResponse } from "./support/env";
import { CHICKEN, NO_PROFILE, OATS, UNKNOWN_EXERCISE, daySummary, entry, profile, weekly } from "./support/nutrition-fixtures";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }), usePathname: () => "/nutrition" }));

const fetchMock = vi.fn<typeof fetch>();

function calls() {
  return fetchMock.mock.calls.map(([url, init]) => ({
    url: String(url),
    method: init?.method ?? "GET",
    body: init?.body ? JSON.parse(String(init.body)) : undefined,
  }));
}

beforeEach(() => {
  fetchMock.mockReset();
  refresh.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  document.cookie = `${CSRF_COOKIE}=${"t".repeat(43)}`;
});

function row(testId: string) {
  return screen.getByTestId(testId).querySelector("dd")?.textContent;
}

describe("daily totals", () => {
  it("show the API's numbers against the targets", () => {
    render(<DailyRings summary={daySummary()} />);
    expect(screen.getByTestId("ring-kcal")).toHaveAttribute("data-value", "1890.4");
    expect(screen.getByTestId("ring-kcal")).toHaveTextContent("1,890 kcal");
    expect(screen.getByTestId("ring-kcal")).toHaveTextContent("of 2,400 kcal");
    expect(screen.getByTestId("ring-protein")).toHaveTextContent("132.5 g");
    expect(screen.getByTestId("ring-protein")).toHaveTextContent("of 140 g");
    expect(screen.getByTestId("ring-carbs")).toHaveTextContent("no target set");
    expect(screen.getByTestId("intake-kcal")).toHaveTextContent("1,890 kcal from 6 entries · 510 kcal to the target");
  });

  it("say when the intake is above the target, as a number", () => {
    render(<DailyRings summary={daySummary({ intake_kcal: 2600, kcal_remaining: -200, macros_complete: false })} />);
    expect(screen.getByTestId("intake-kcal")).toHaveTextContent("200 kcal above the target");
    expect(screen.getByText(/macro totals leave them out/)).toBeInTheDocument();
  });
});

describe("energy balance card", () => {
  it("labels every estimate and shows the numbers when complete", () => {
    render(<EnergyBalanceCard summary={daySummary()} />);
    expect(screen.getByRole("heading", { name: "Energy balance (estimate)" })).toBeInTheDocument();
    expect(row("row-intake")).toBe("1,890 kcal");
    expect(row("row-bmr")).toBe("1,756 kcal");
    expect(row("row-baseline")).toBe("2,414 kcal");
    expect(row("row-exercise")).toBe("612 kcal");
    expect(row("row-expenditure")).toBe("3,026 kcal");
    expect(row("row-balance")).toBe("−1,135 kcal");
    for (const id of ["row-bmr", "row-baseline", "row-expenditure", "row-balance"]) {
      expect(screen.getByTestId(id)).toHaveTextContent("estimate");
    }
  });

  it("shows unknown, never a number, when an activity has no energy", () => {
    render(<EnergyBalanceCard summary={daySummary(UNKNOWN_EXERCISE)} />);
    expect(row("row-exercise")).toBe("612 kcal + unknown");
    expect(screen.getByTestId("row-exercise")).toHaveTextContent("1 activity has no energy data");
    expect(row("row-expenditure")).toBe("unknown");
    expect(row("row-balance")).toBe("unknown");
  });

  it("shows unknown and why when there is no profile", () => {
    render(<EnergyBalanceCard summary={daySummary(NO_PROFILE)} />);
    expect(row("row-bmr")).toBe("unknown");
    expect(row("row-baseline")).toBe("unknown");
    expect(row("row-balance")).toBe("unknown");
    expect(screen.getByText("Add a profile (below) to estimate the basal rate.")).toBeInTheDocument();
  });
});

describe("week", () => {
  it("shows the API's averages and days", () => {
    render(<WeeklyAverages weekly={weekly()} />);
    const totals = screen.getByTestId("week-totals");
    expect(totals).toHaveTextContent("1,995 kcal");
    expect(totals).toHaveTextContent("2 of 3");
    expect(totals).toHaveTextContent("126.3 g"); // (120 + 132.5) / 2 days logged
    const rows = screen.getByTestId("week-table").querySelectorAll("tbody tr");
    expect([...rows].map((r) => Number(r.getAttribute("data-intake")))).toEqual([2100, 0, 1890.4]);
  });

  it("finds the ISO week", () => {
    expect(weekStart("2026-10-18")).toBe("2026-10-12"); // Sunday
    expect(weekStart("2026-10-12")).toBe("2026-10-12");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(scaled(372, 80)).toBeCloseTo(297.6);
    expect(scaled(null, 80)).toBeNull();
  });
});

describe("meal list", () => {
  it("groups by meal and removes an entry", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    render(<MealList entries={[entry(), entry({ client_id: "c2", meal: "lunch", food_name: "Rice", kcal: 260, brand: null })]} />);
    expect(screen.getByRole("region", { name: "Breakfast" })).toHaveTextContent("298 kcal");
    expect(screen.getByRole("region", { name: "Lunch" })).toHaveTextContent("Rice");
    await userEvent.click(screen.getByRole("button", { name: "Remove Rice from lunch" }));
    expect(calls()[0]).toMatchObject({ url: "/api/ts/v1/nutrition/log/c2", method: "DELETE" });
    expect(refresh).toHaveBeenCalled();
  });
});

describe("add food", () => {
  it("works with the keyboard only: search, pick, grams, add", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ items: [CHICKEN] }))
      .mockResolvedValueOnce(jsonResponse(entry({ food_id: CHICKEN.id, grams: 150 }), 201));
    render(<AddFood date="2026-10-18" favorites={[OATS]} recent={[]} newId={() => "11111111-1111-4111-8111-111111111111"} />);

    // Meal select first: pick lunch with the arrow keys.
    await user.tab();
    expect(screen.getByLabelText("Meal")).toHaveFocus();
    await user.selectOptions(screen.getByLabelText("Meal"), "lunch");
    await user.tab();
    expect(screen.getByLabelText("Search foods")).toHaveFocus();
    await user.keyboard("chicken{Enter}");
    expect(calls()[0]).toMatchObject({ url: "/api/ts/v1/nutrition/foods?q=chicken&limit=20", method: "GET" });

    const result = await screen.findByRole("button", { name: /Chicken breast, cooked/ });
    // Tab to the result and press Enter.
    for (let i = 0; i < 10 && document.activeElement !== result; i++) await user.tab();
    expect(result).toHaveFocus();
    await user.keyboard("{Enter}");

    const gramsInput = await screen.findByLabelText("Grams");
    await vi.waitFor(() => expect(gramsInput).toHaveFocus());
    await user.clear(gramsInput);
    await user.keyboard("150");
    expect(screen.getByTestId("live-preview")).toHaveTextContent("248 kcal · protein 46.5 g · carbs 0 g · fat 5.4 g");
    await user.keyboard("{Enter}");

    expect(await screen.findByText("Added 150 g Chicken breast, cooked to lunch.")).toBeInTheDocument();
    expect(calls()[1]).toEqual({
      url: "/api/ts/v1/nutrition/log/11111111-1111-4111-8111-111111111111",
      method: "PUT",
      body: { date: "2026-10-18", meal: "lunch", food_id: 8, grams: 150 },
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("creates a food and logs it", async () => {
    const user = userEvent.setup();
    const created = { ...CHICKEN, id: 99, name: "Lentil soup", kcal_100g: 80 };
    fetchMock.mockResolvedValueOnce(jsonResponse(created, 201)).mockResolvedValueOnce(jsonResponse(entry({ food_id: 99 }), 201));
    render(<AddFood date="2026-10-18" favorites={[]} recent={[]} newId={() => "22222222-2222-4222-8222-222222222222"} />);
    await user.click(screen.getByRole("button", { name: "Create a food" }));
    const form = screen.getByRole("form", { name: "New food" });
    await user.type(within(form).getByLabelText("Name"), "Lentil soup");
    await user.type(within(form).getByLabelText("kcal"), "80");
    await user.type(within(form).getByLabelText("Protein g"), "6");
    await user.click(within(form).getByRole("button", { name: "Save food" }));
    expect(calls()[0]).toEqual({
      url: "/api/ts/v1/nutrition/foods",
      method: "POST",
      body: { name: "Lentil soup", brand: null, kcal_100g: 80, protein_100g: 6, carbs_100g: null, fat_100g: null, favorite: false },
    });
    await user.click(await screen.findByRole("button", { name: "Add to breakfast" }));
    expect(calls()[1]).toMatchObject({ method: "PUT", body: { food_id: 99, grams: 100, meal: "breakfast" } });
  });

  it("says when Open Food Facts is switched off", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [], remote: "disabled" }));
    render(<AddFood date="2026-10-18" favorites={[]} recent={[]} />);
    await user.type(screen.getByLabelText("Search foods"), "oats");
    await user.click(screen.getByRole("button", { name: "Search Open Food Facts too" }));
    expect(await screen.findByText("Open Food Facts lookups are switched off; showing saved foods only.")).toBeInTheDocument();
    expect(calls()[0]!.url).toBe("/api/ts/v1/nutrition/foods/lookup?q=oats");
  });
});

describe("profile form", () => {
  it("shows the below-BMR note as information and keeps the target", async () => {
    const user = userEvent.setup();
    const note = "kcal_target (1500 kcal) is below the estimated basal metabolic rate (1755.5 kcal). It was saved as entered; the BMR is an estimate.";
    fetchMock.mockResolvedValueOnce(jsonResponse(profile({ kcal_target: 1500, warning: note })));
    render(<ProfileForm profile={profile()} date="2026-10-18" />);
    const target = screen.getByLabelText("kcal target (optional)");
    await user.clear(target);
    await user.type(target, "1500");
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(await screen.findByTestId("profile-note")).toHaveTextContent(note);
    expect(screen.getByRole("note")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Profile saved.");
    expect(calls()[0]).toMatchObject({ url: "/api/ts/v1/nutrition/profile", method: "PUT", body: { kcal_target: 1500, birth_year: 1990, height_cm: 180 } });
  });

  it("saves the body weight for the day", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(jsonResponse({ date: "2026-10-18", weight_kg: 78.2 }));
    render(<ProfileForm profile={null} date="2026-10-18" />);
    await user.type(screen.getByLabelText("Body weight on 2026-10-18 (kg)"), "78,2");
    await user.click(screen.getByRole("button", { name: "Save weight" }));
    expect(calls()[0]).toEqual({ url: "/api/ts/v1/training/body-metrics/2026-10-18", method: "PUT", body: { weight_kg: 78.2 } });
  });
});
