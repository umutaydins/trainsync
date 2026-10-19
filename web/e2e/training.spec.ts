import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import type { DayLog, DaySummary } from "@/features/nutrition/types";
import type { WorkoutDetail, WorkoutPage } from "@/features/training/types";

const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";
const API_KEY = process.env.E2E_API_KEY ?? "dev-key-1";
const EMAIL = process.env.E2E_EMAIL ?? "owner@example.com";
const PASSWORD = process.env.E2E_PASSWORD ?? "dev-e2e-owner-password";
const PHONE = { width: 375, height: 812 };
const AXE = createRequire(import.meta.url).resolve("axe-core/axe.min.js");

function screenshotPath(name: string): string {
  return fileURLToPath(new URL(`../../docs/img/${name}.png`, import.meta.url));
}

async function apiGet<T>(request: APIRequestContext, path: string, params: Record<string, string> = {}): Promise<T> {
  const response = await request.get(`${API_URL}${path}`, { params, headers: { "X-API-Key": API_KEY } });
  expect(response.ok(), `${path} → ${response.status()}`).toBeTruthy();
  return (await response.json()) as T;
}

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/$/);
}

/** axe-core (the same package the unit tests use), injected into the page; all rules. */
async function expectNoAxeViolations(page: Page, what: string) {
  await page.addScriptTag({ path: AXE });
  const violations = await page.evaluate(async () => {
    const result = await (window as unknown as { axe: { run: (ctx: Document) => Promise<{ violations: { id: string; nodes: { target: string[] }[] }[] }> } }).axe.run(document);
    return result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  });
  expect(violations, `axe on ${what}`).toEqual([]);
}

async function noHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, "page scrolls sideways").toBeLessThanOrEqual(0);
}

test("training and nutrition: program → workout with rest timer → history; two foods → today's kcal", async ({ page, request }) => {
  await test.step("the PWA manifest is served without a session", async () => {
    const manifest = await request.get("/manifest.webmanifest");
    expect(manifest.status()).toBe(200);
    expect(await manifest.json()).toMatchObject({ start_url: "/training", display: "standalone", short_name: "trainsync" });
    expect((await request.get("/icons/icon-192.png")).status()).toBe(200);
  });

  await login(page);
  await page.setViewportSize(PHONE);

  await test.step("generate a program, save it and activate it", async () => {
    await page.goto("/training/programs");
    await page.getByLabel("Days per week").selectOption("4");
    await page.getByRole("button", { name: "Generate preview" }).click();
    const editor = page.getByTestId("program-editor");
    await expect(editor.getByTestId("editor-day")).toHaveCount(4);
    await noHorizontalScroll(page);
    await expectNoAxeViolations(page, "/training/programs (preview)");
    await page.screenshot({ path: screenshotPath("programs"), fullPage: true });
    await page.getByRole("button", { name: "Save program" }).click();
    await expect(page.getByRole("status")).toContainText("Saved");
    await page.getByRole("button", { name: "Activate it" }).click();
    await expect(page.getByRole("status")).toContainText("Program activated");
    await expect(page.getByTestId("program-list").getByText("Active")).toBeVisible();
  });

  let workoutId = 0;
  const kg = 60;
  const reps = 8;

  await test.step("start day 1 and log 3 sets; the rest timer starts", async () => {
    await page.goto("/training");
    await page.getByTestId("program-days").getByRole("button").first().click();
    await expect(page).toHaveURL(/\/training\/workout\/\d+$/);
    workoutId = Number(page.url().split("/").pop());
    const screen = page.getByTestId("workout-screen");
    await expect(screen).toBeVisible();

    const first = screen.locator("section[data-exercise-id]").first();
    const name = (await first.getByRole("heading", { level: 2 }).textContent()) ?? "";
    for (const set of [1, 2, 3]) {
      await first.getByLabel(`Reps, ${name} set ${set}`).fill(String(reps));
      await first.getByLabel(`Weight in kg, ${name} set ${set}`).fill(String(kg));
      await first.getByRole("button", { name: `Log ${name} set ${set}` }).click();
      await expect(first.getByTestId("set-row").nth(set - 1)).toHaveAttribute("data-status", "saved");
      // The rest timer takes the whole screen; "Hide timer" shrinks it to a bar for the next set.
      const timer = page.getByRole("dialog", { name: "Rest" });
      await expect(timer).toBeVisible();
      await expect(timer.getByTestId("rest-remaining")).toHaveText(/^\d+:\d\d$/);
      await timer.getByRole("button", { name: "Hide timer" }).click();
      await expect(page.getByTestId("rest-timer")).toBeVisible();
    }
    await noHorizontalScroll(page);
    await expectNoAxeViolations(page, "/training/workout (rest timer)");

    const api = await apiGet<WorkoutDetail>(request, `/v1/training/workouts/${workoutId}`);
    expect(api.sets).toHaveLength(3);
    expect(api.volume_kg).toBe(3 * reps * kg);
    expect(new Set(api.sets.map((s) => s.client_id)).size).toBe(3);

    // The plate calculator for the barbell lift, over the running rest timer (README screenshot).
    await first.getByRole("button", { name: "Plates" }).click();
    const sheet = page.getByRole("dialog", { name: `Plates for ${kg} kg` });
    await expect(sheet.getByTestId("plates-per-side")).toHaveText("20");
    await expect(sheet.locator('rect[data-side="left"]')).toHaveCount(1);
    await page.screenshot({ path: screenshotPath("workout") });
    await sheet.getByRole("button", { name: "Done" }).click();
    await expect(sheet).toBeHidden();
  });

  await test.step("finish; the summary and the history show the volume", async () => {
    await page.getByRole("button", { name: "Finish workout" }).click();
    const summary = page.getByTestId("workout-summary");
    await expect(summary).toContainText((3 * reps * kg).toLocaleString("en-GB") + " kg");
    await page.getByRole("link", { name: "Open in history" }).click();
    await expect(page).toHaveURL(new RegExp(`/training/history/${workoutId}$`));
    await expect(page.getByTestId("workout-summary")).toHaveAttribute("data-volume", String(3 * reps * kg));

    await page.goto("/training/history");
    const listed = await apiGet<WorkoutPage>(request, "/v1/training/workouts", { limit: "20" });
    const row = page.getByTestId("workout-history").locator(`li[data-workout-id="${workoutId}"]`);
    await expect(row).toHaveAttribute("data-volume", String(listed.items.find((w) => w.id === workoutId)?.volume_kg));
    await expect(row).toContainText((3 * reps * kg).toLocaleString("en-GB") + " kg");
    await expectNoAxeViolations(page, "/training/history");
  });

  await test.step("progress shows the lift", async () => {
    await page.goto("/training/progress");
    await expect(page.getByTestId("exercise-chart")).toBeVisible();
    await expect(page.getByTestId("pr-board")).toBeVisible();
    await expect(page.getByTestId("muscle-chart").locator(".recharts-bar-rectangle").first()).toBeVisible();
    await noHorizontalScroll(page);
    await expectNoAxeViolations(page, "/training/progress");
    await page.screenshot({ path: screenshotPath("progress"), fullPage: true });
  });

  await test.step("create two foods, log both; today's kcal is their sum", async () => {
    await page.goto("/nutrition");
    // Add food is a bottom sheet on the phone; it stays open while a meal is logged.
    await page.getByRole("button", { name: "Add food" }).click();
    const add = page.getByTestId("add-food");
    const foods = [
      { name: "E2E oats", kcal100: 380, protein: 13, grams: 50, meal: "breakfast" },
      { name: "E2E yogurt", kcal100: 60, protein: 10, grams: 200, meal: "lunch" },
    ];
    for (const food of foods) {
      await add.getByLabel("Meal").selectOption(food.meal);
      await add.getByRole("button", { name: "Create a food" }).click();
      const form = add.getByRole("form", { name: "New food" });
      await form.getByLabel("Name").fill(food.name);
      await form.getByLabel("kcal").fill(String(food.kcal100));
      await form.getByLabel("Protein g").fill(String(food.protein));
      await form.getByRole("button", { name: "Save food" }).click();
      await add.getByLabel("Grams").fill(String(food.grams));
      await add.getByRole("button", { name: `Add to ${food.meal}` }).click();
      await expect(add.getByRole("status")).toHaveText(`Added ${food.grams} g ${food.name} to ${food.meal}.`);
    }
    await noHorizontalScroll(page);
    await expectNoAxeViolations(page, "/nutrition (add-food sheet)");
    await page.keyboard.press("Escape");
    await expect(add).toBeHidden();
    const expected = foods.reduce((sum, f) => sum + (f.kcal100 * f.grams) / 100, 0);
    await expect(page.getByTestId("log-entry")).toHaveCount(2);

    // The Food page's day is the user's local day (the `tz` cookie the BFF sets), not UTC.
    const zone = (await page.context().cookies()).find((c) => c.name === "tz")?.value ?? "UTC";
    const today = new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
    const log = await apiGet<DayLog>(request, "/v1/nutrition/log", { date: today });
    const summary = await apiGet<DaySummary>(request, "/v1/nutrition/summary", { date: today });
    expect(log.entries.reduce((sum, e) => sum + e.kcal, 0)).toBe(expected);
    expect(summary.intake_kcal).toBe(expected);
    await expect(page.getByTestId("intake-kcal")).toHaveAttribute("data-value", String(expected));
    await expect(page.getByTestId("intake-kcal")).toContainText(`${expected} kcal`);
    // No profile yet: the balance is unknown, not guessed.
    await expect(page.getByTestId("row-balance").locator("dd")).toHaveText("unknown");
    await noHorizontalScroll(page);
    await expectNoAxeViolations(page, "/nutrition");
    await page.screenshot({ path: screenshotPath("nutrition"), fullPage: true });

    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await expect(page.getByTestId("tile-intake")).toContainText(`${expected} kcal`);
    await expect(page.getByTestId("tile-gym")).toContainText("1 session");
  });
});
