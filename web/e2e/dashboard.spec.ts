import { fileURLToPath } from "node:url";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { formatCount, formatDuration, formatKm, formatMeters } from "../lib/format";
import type { StatsSummary, WeeklyStats } from "../lib/types";

const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";
const API_KEY = process.env.E2E_API_KEY ?? "dev-key-1";
const PASSWORD = process.env.E2E_PASSWORD ?? "dev-only-dashboard-password";
// fake_strava's seeded history ends on 2026-01-01; this range holds most of it.
const RANGE = { from: "2025-03-01", to: "2025-12-31" };

function screenshotPath(name: string): string {
  return fileURLToPath(new URL(`../../docs/img/${name}.png`, import.meta.url));
}

async function apiGet<T>(request: APIRequestContext, path: string, params: Record<string, string>): Promise<T> {
  const response = await request.get(`${API_URL}${path}`, { params, headers: { "X-API-Key": API_KEY } });
  expect(response.ok(), `${path} → ${response.status()}`).toBeTruthy();
  return (await response.json()) as T;
}

async function tile(page: Page, label: string): Promise<string> {
  const term = page.getByTestId("kpis").locator("dt", { hasText: label });
  return (await term.locator("xpath=following-sibling::dd[1]").textContent()) ?? "";
}

test("log in, connect Strava, backfill, dashboard matches the API, activity, sync", async ({ page, request }) => {
  await test.step("the dashboard needs a login", async () => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
    await page.getByLabel("Password").fill("wrong password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.locator("#login-error")).toHaveText("Wrong password.");
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });

  await test.step("connect Strava through the fake OAuth and land back on /sync", async () => {
    await page.goto("/sync");
    await page.getByRole("link", { name: "Connect Strava" }).click();
    await expect(page).toHaveURL(/\/sync\?connected=1$/);
    await expect(page.getByText("Strava connected.")).toBeVisible();
  });

  await test.step("the backfill succeeds", async () => {
    await expect(async () => {
      await page.reload();
      await expect(page.getByTestId("run-backfill")).toHaveAttribute("data-status", "succeeded", { timeout: 1000 });
    }).toPass({ timeout: 120_000, intervals: [2000] });
    await expect(page.getByTestId("run-backfill").getByText("succeeded")).toBeVisible();
  });

  await test.step("dashboard KPIs equal /v1/stats/summary and the chart equals /v1/stats/weekly", async () => {
    await page.goto(`/?from=${RANGE.from}&to=${RANGE.to}`);
    const kpis = page.getByTestId("kpis");
    await expect(kpis).toHaveAttribute("data-from", RANGE.from);
    await expect(kpis).toHaveAttribute("data-to", RANGE.to);

    const summary = await apiGet<StatsSummary>(request, "/v1/stats/summary", RANGE);
    expect(summary.totals.count).toBeGreaterThan(0);
    expect(await tile(page, "Distance")).toBe(formatKm(summary.totals.distance_m, 1));
    expect(await tile(page, "Moving time")).toBe(formatDuration(summary.totals.moving_time_s));
    expect(await tile(page, "Elevation")).toBe(formatMeters(summary.totals.elevation_gain_m));
    expect(await tile(page, "Activities")).toBe(formatCount(summary.totals.count));

    const weekly = await apiGet<WeeklyStats>(request, "/v1/stats/weekly", RANGE);
    const rows = page.getByTestId("weekly-table").locator("tbody tr");
    await expect(rows).toHaveCount(weekly.weeks.length);
    const shown = await rows.evaluateAll((trs) =>
      trs.map((tr) => ({
        week_start: tr.getAttribute("data-week"),
        count: Number(tr.getAttribute("data-count")),
        distance_m: Number(tr.getAttribute("data-distance")),
      })),
    );
    expect(shown).toEqual(weekly.weeks.map((w) => ({ week_start: w.week_start, count: w.count, distance_m: w.distance_m })));
    expect(weekly.weeks.reduce((sum, w) => sum + w.count, 0)).toBe(summary.totals.count);

    await expect(page.getByTestId("weekly-chart").locator(".recharts-bar-rectangle").first()).toBeVisible();
    await page.screenshot({ path: screenshotPath("dashboard"), fullPage: true });
    await page.emulateMedia({ colorScheme: "dark" });
    await page.waitForTimeout(400); // let colour transitions finish
    await page.screenshot({ path: screenshotPath("dashboard-dark"), fullPage: true });
    await page.emulateMedia({ colorScheme: "light" });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(400);
    await page.screenshot({ path: screenshotPath("dashboard-mobile"), fullPage: true });
    await page.setViewportSize({ width: 1280, height: 800 });
  });

  await test.step("activity list pages with Load more, then an activity opens", async () => {
    await page.goto("/activities");
    const rows = page.getByTestId("activity-table").locator("tbody tr");
    await expect(rows).toHaveCount(50);
    await expect(rows.first()).toBeVisible();
    await expect(page.getByRole("status", { name: "Loading activities" })).toHaveCount(0);
    await page.screenshot({ path: screenshotPath("activities"), fullPage: false });
    await page.getByRole("button", { name: "Load more" }).click();
    await expect(rows).toHaveCount(100);
    const ids = await rows.evaluateAll((trs) => trs.map((tr) => tr.getAttribute("data-activity-id")));
    expect(new Set(ids).size).toBe(100);

    const first = rows.first().getByRole("link");
    const name = (await first.textContent()) ?? "";
    await first.click();
    await expect(page).toHaveURL(/\/activities\/\d+$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(name);
    await expect(page.getByTestId("activity-detail")).toContainText("Distance");
    await page.screenshot({ path: screenshotPath("activity"), fullPage: true });
  });

  await test.step("the sync page shows the succeeded backfill", async () => {
    await page.goto("/sync");
    await expect(page.getByTestId("run-backfill")).toHaveAttribute("data-status", "succeeded");
    await expect(page.getByRole("progressbar", { name: "15 minutes" })).toBeVisible();
    await page.screenshot({ path: screenshotPath("sync"), fullPage: true });
  });

  await test.step("the browser never sees the API key", async () => {
    const response = await page.request.get("/api/ts/v1/stats/summary");
    expect(response.status()).toBe(200);
    expect(await response.text()).not.toContain(API_KEY);
    const html = await (await page.request.get("/")).text();
    expect(html).not.toContain(API_KEY);
  });
});
