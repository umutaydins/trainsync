import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AddFood } from "@/features/nutrition/components/add-food";
import { NutritionView } from "@/features/nutrition/components/nutrition-view";
import { ProfileForm } from "@/features/nutrition/components/profile-form";
import type { FoodDay } from "@/features/nutrition/load";
import { ProfileStep } from "@/features/onboarding/components/profile-step";
import { CSRF_COOKIE } from "@/lib/csrf-cookie";
import { violations } from "./support/axe";
import { jsonResponse } from "./support/env";
import { renderWithIntl } from "./support/intl";
import { CHICKEN, OATS, daySummary, entry, profile, weekly } from "./support/nutrition-fixtures";

vi.mock("server-only", () => ({}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }), usePathname: () => "/nutrition" }));

const fetchMock = vi.fn<typeof fetch>();

function phone(isPhone: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: !isPhone && query.includes("min-width"), addEventListener: () => undefined, removeEventListener: () => undefined }));
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  phone(false);
  document.cookie = `${CSRF_COOKIE}=${"t".repeat(43)}`;
});

function foodDay(overrides: Partial<FoodDay> = {}): FoodDay {
  return {
    date: "2026-10-18",
    today: "2026-10-18",
    summary: { ok: true, data: daySummary() },
    log: { ok: true, data: { date: "2026-10-18", entries: [entry()] } },
    weekly: { ok: true, data: weekly() },
    favorites: [OATS],
    recent: [CHICKEN],
    profile: profile(),
    defaultMeal: "lunch",
    ...overrides,
  };
}

describe("add food in a bottom sheet", () => {
  it("on a phone: favourite → grams stepper → added to the meal of the hour", async () => {
    phone(true);
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(jsonResponse(entry({ food_id: OATS.id, grams: 120 }), 201));
    renderWithIntl(<AddFood date="2026-10-18" favorites={[OATS]} recent={[]} defaultMeal="lunch" newId={() => "33333333-3333-4333-8333-333333333333"} />);
    await user.click(screen.getByRole("button", { name: "Add food" }));
    const sheet = await screen.findByRole("dialog", { name: "Add food" });
    expect(within(sheet).getByLabelText("Meal")).toHaveValue("lunch");
    await user.click(within(sheet).getByRole("button", { name: /Rolled oats/ }));
    await user.click(within(sheet).getByRole("button", { name: "More grams" }));
    await user.click(within(sheet).getByRole("button", { name: "More grams" }));
    expect(within(sheet).getByLabelText("Grams")).toHaveValue("120");
    expect(within(sheet).getByRole("button", { name: "More grams" })).toHaveClass("size-16");
    await user.click(within(sheet).getByRole("button", { name: "Add to lunch" }));
    expect(await within(sheet).findByRole("status")).toHaveTextContent("Added 120 g Rolled oats to lunch.");
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({ date: "2026-10-18", meal: "lunch", food_id: OATS.id, grams: 120 });
  });

  it("checks the barcode and the grams, in Turkish", async () => {
    const user = userEvent.setup();
    renderWithIntl(<AddFood date="2026-10-18" favorites={[OATS]} recent={[]} />, "tr");
    await user.click(screen.getByRole("button", { name: "Yiyecek ekle" }));
    await user.type(screen.getByLabelText("Barkod"), "123");
    await user.click(screen.getByRole("button", { name: "Bul" }));
    expect(screen.getByText("Barkod: 8 ile 14 rakam")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Rolled oats/ }));
    await user.clear(screen.getByLabelText("Gram"));
    await user.click(screen.getByRole("button", { name: "kahvaltı öğününe ekle" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Gram: 0'dan büyük, en fazla 5000");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("says when the backend is down instead of the API's text", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(jsonResponse({ error: "trainsync API unavailable" }, 502));
    renderWithIntl(<AddFood date="2026-10-18" favorites={[]} recent={[]} />);
    await user.click(screen.getByRole("button", { name: "Add food" }));
    await user.type(screen.getByLabelText("Search foods"), "oats{Enter}");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("backend is not answering");
    expect(alert).not.toHaveTextContent("trainsync API unavailable");
  });
});

describe("one profile form for Food and the onboarding", () => {
  it("shows the same fields and rules in both places", async () => {
    const user = userEvent.setup();
    renderWithIntl(<ProfileForm profile={null} date="2026-10-18" />);
    const labels = ["Sex (for the equation)", "Birth year", "Height (cm)", "Everyday activity (outside logged exercise)", "Daily kcal target (optional)", "Protein target in g (optional)"];
    for (const label of labels) expect(screen.getByLabelText(label)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Birth year"), "1850");
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(screen.getByText("Enter a year from 1900 to 2100.")).toBeInTheDocument();
    cleanup();

    renderWithIntl(<ProfileStep onNext={vi.fn()} profile={profile()} />);
    for (const label of labels) expect(screen.getByLabelText(label)).toBeInTheDocument();
    expect(screen.getByLabelText("Height (cm)")).toHaveValue("180");
  });

  it("speaks Turkish", () => {
    renderWithIntl(<ProfileForm profile={profile()} date="2026-10-18" />, "tr");
    expect(screen.getByLabelText("Doğum yılı")).toHaveValue("1990");
    expect(screen.getByRole("button", { name: "Profili kaydet" })).toBeInTheDocument();
  });
});

describe("the Food page", () => {
  it("shows the day in the user's language with date navigation, never past today", () => {
    renderWithIntl(<NutritionView data={foodDay({ date: "2026-10-17" })} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Food");
    expect(screen.getByText("Saturday, October 17, 2026")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Previous day" })).toHaveAttribute("href", "/nutrition?date=2026-10-16");
    expect(screen.getByRole("link", { name: "Next day" })).toHaveAttribute("href", "/nutrition?date=2026-10-18");
    expect(screen.getByRole("link", { name: "Today" })).toHaveAttribute("href", "/nutrition");
    cleanup();
    renderWithIntl(<NutritionView data={foodDay()} />);
    expect(screen.queryByRole("link", { name: "Next day" })).toBeNull();
  });

  it("one failing block does not take the page down, and the API's text is not shown", () => {
    renderWithIntl(<NutritionView data={foodDay({ log: { ok: false, status: 502, error: "trainsync API unavailable" } })} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load the food log");
    expect(screen.getByRole("alert")).not.toHaveTextContent("trainsync API unavailable");
    expect(screen.getByTestId("ring-kcal")).toBeInTheDocument();
  });

  it.each(["en", "tr"] as const)("has no axe violations (%s)", async (locale) => {
    expect(await violations(<NutritionView data={foodDay()} />, locale)).toEqual([]);
  });
});
