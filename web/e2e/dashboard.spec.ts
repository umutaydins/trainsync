import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

import type { ProgressSummary } from "@/features/progress/types";

import { API_KEY, DESKTOP, OWNER, apiGet, arrived, gotoReady, settled } from "./support";

function screenshotPath(name: string): string {
  return fileURLToPath(new URL(`../../docs/img/${name}.png`, import.meta.url));
}

test("log in, connect Strava, backfill, Today and Progress match the API, activity, sync", async ({ page, request }) => {
  await test.step("Today needs a login", async () => {
    await gotoReady(page, "/");
    await expect(page).toHaveURL(/\/login$/);
    await page.getByLabel("Email").fill(OWNER.email);
    await page.getByLabel("Password").fill("wrong password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.locator("#login-error")).toHaveText("Wrong email or password.");
    await page.getByLabel("Password").fill(OWNER.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await arrived(page, /\/$/);
    await expect(page.getByTestId("today")).toBeVisible();
  });

  await test.step("connect Strava through the fake OAuth and land back on /sync", async () => {
    await gotoReady(page, "/sync");
    await page.getByRole("link", { name: "Connect Strava" }).click();
    await arrived(page, /\/sync\?connected=1$/);
    await expect(page.getByText("Strava connected.")).toBeVisible();
  });

  await test.step("the backfill succeeds", async () => {
    await expect(async () => {
      await page.reload();
      await settled(page);
      await expect(page.getByTestId("run-backfill")).toHaveAttribute("data-status", "succeeded", { timeout: 1000 });
    }).toPass({ timeout: 120_000, intervals: [2000] });
    await expect(page.getByTestId("run-backfill").getByText("Succeeded")).toBeVisible();
  });

  await test.step("Today greets the user; Progress equals /v1/stats/summary and follows the period", async () => {
    await gotoReady(page, "/");
    await expect(page.getByTestId("today")).toBeVisible();
    await expect(page.getByTestId("today-activity")).toBeVisible();

    // fake_strava seeds the year before "now", so all time has data.
    await gotoReady(page, "/progress?period=all");
    const summary = await apiGet<ProgressSummary>(request, "/v1/stats/summary", { period: "all" });
    expect(summary.endurance.totals.count.value).toBeGreaterThan(0);
    await expect(page.getByTestId("stat-activities")).toHaveAttribute("data-value", String(summary.endurance.totals.count.value));
    await expect(page.getByTestId("volume-chart").locator(".recharts-bar-rectangle").first()).toBeVisible();

    await page.getByRole("radio", { name: "This week" }).click();
    await expect(page).toHaveURL(/\/progress\?period=week$/);
    const blocks = page.locator("[data-block]");
    await expect(blocks.first()).toBeVisible();
    for (const block of await blocks.all()) await expect(block).toHaveAttribute("data-period", "week");

    await gotoReady(page, "/progress?period=all");
    await page.screenshot({ path: screenshotPath("dashboard"), fullPage: true });
    await page.emulateMedia({ colorScheme: "dark" });
    await page.waitForTimeout(400); // let colour transitions finish
    await page.screenshot({ path: screenshotPath("dashboard-dark"), fullPage: true });
    await page.emulateMedia({ colorScheme: "light" });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(400);
    await page.screenshot({ path: screenshotPath("dashboard-mobile"), fullPage: true });
    await page.setViewportSize(DESKTOP);
  });

  await test.step("activity list pages with Load more, then an activity opens", async () => {
    await gotoReady(page, "/activities");
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
    await gotoReady(page, "/sync");
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
