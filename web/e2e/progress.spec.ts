import { expect, test } from "@playwright/test";

import { createUser, gotoReady, login, seedWorkout } from "./support";

const ZONE = "Europe/Berlin";
const DAY_MS = 24 * 60 * 60 * 1000;
/** Workouts this many days back: today, and then spread so the periods count differently. */
const DAYS_AGO = [0, 10, 60, 400] as const;

/** The user's local day (`YYYY-MM-DD`) `daysAgo` days back. */
function localDay(daysAgo: number): string {
  const format = new Intl.DateTimeFormat("en-CA", { timeZone: ZONE, year: "numeric", month: "2-digit", day: "2-digit" });
  return format.format(new Date(Date.now() - daysAgo * DAY_MS));
}

/** The first local day of each period (weeks start on Monday). */
function periodStarts(): Record<"week" | "month" | "year" | "all", string> {
  const today = localDay(0);
  const weekday = (new Date(`${today}T12:00:00Z`).getUTCDay() + 6) % 7;
  return { week: localDay(weekday), month: `${today.slice(0, 8)}01`, year: `${today.slice(0, 5)}01-01`, all: "0000-01-01" };
}

const PERIODS = [
  { period: "week", label: "This week" },
  { period: "month", label: "This month" },
  { period: "year", label: "This year" },
  { period: "all", label: "All time" },
] as const;

test("progress: W → M → Y → All moves every block, the URL, the stats; charts and the heatmap render", async ({ page, request }) => {
  // A fresh account with workouts spread over time: the counts below do not depend on other specs.
  const user = await createUser(request, "progress", ZONE);
  const starts = periodStarts();
  const sessionsIn = (period: keyof typeof starts) => DAYS_AGO.filter((daysAgo) => localDay(daysAgo) >= starts[period]).length;
  for (const daysAgo of DAYS_AGO) await seedWorkout(request, user.token, { daysAgo, kg: 60, reps: 5 });
  await login(page, user);
  await gotoReady(page, "/progress?period=week");

  const blocks = page.locator("[data-block]");
  for (const { period, label } of PERIODS) {
    await test.step(`${label}`, async () => {
      await page.getByRole("radio", { name: label }).click();
      await expect(page).toHaveURL(new RegExp(`/progress\\?period=${period}$`));
      await expect(page.getByTestId("progress")).toHaveAttribute("data-period", period);
      await expect(page.getByRole("radio", { name: label })).toHaveAttribute("aria-checked", "true");
      await expect(blocks.first()).toBeVisible();
      expect(await blocks.count()).toBeGreaterThan(3);
      for (const block of await blocks.all()) await expect(block).toHaveAttribute("data-period", period);
      await expect(page.getByTestId("stat-sessions")).toHaveAttribute("data-value", String(sessionsIn(period)));
      // No Strava here: the volume chart shows the lifted tonnage.
      await page.getByRole("region", { name: "Volume" }).getByRole("radio", { name: "Tonnage" }).click();
      await expect(page.getByTestId("volume-chart").locator(".recharts-bar-rectangle").first()).toBeVisible();
    });
  }

  await test.step("the heatmap shows the last 12 months up to today, never a future day", async () => {
    const heatmap = page.getByTestId("heatmap");
    await expect(heatmap.getByRole("grid")).toBeVisible();
    await expect(heatmap.getByTestId("heatmap-range")).toHaveText("Last 12 months");
    const lastYear = DAYS_AGO.filter((daysAgo) => daysAgo < 365).length;
    await expect(heatmap.locator('[role="gridcell"][data-level]:not([data-level="0"])')).toHaveCount(lastYear);
    const days = (await heatmap.locator("[data-day]").evaluateAll((cells) => cells.map((c) => c.getAttribute("data-day") ?? ""))).sort();
    expect(days).toHaveLength(365);
    expect(days.at(-1)).toBe(localDay(0));
  });
});
