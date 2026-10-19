import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { test, type Page } from "@playwright/test";

import {
  APP_PAGES,
  NOT_FOUND_PAGE,
  DESKTOP,
  PHONE,
  OWNER,
  PUBLIC_PAGES,
  THEMES,
  apiGet,
  apiSession,
  createUser,
  gotoReady,
  login,
  seedWorkout,
  setTheme,
} from "./support";

/** Review screenshots (P8.17), only on request: `SCREENSHOTS_DIR=~/trainsync-screens`. */
const DIR = process.env.SCREENSHOTS_DIR ?? "";
const WIDTHS = [PHONE, DESKTOP] as const;
/** The owner's lifting history for the shots, added once (only when the owner has no workouts). */
const OWNER_WORKOUTS_DAYS_AGO = [1, 3, 8, 15, 30, 45] as const;

test.skip(!DIR, "set SCREENSHOTS_DIR to take the review screenshots");
test.use({ reducedMotion: "reduce" });
test.describe.configure({ timeout: 600_000 });

/** `/` → today, `/training/history/12` → training-history-detail, `/me/profile` → me-profile. */
function pageName(url: string): string {
  if (url === "/") return "today";
  return url
    .slice(1)
    .replace(/\/\d+$/, "/detail")
    .replaceAll("/", "-");
}

async function shoot(page: Page, url: string, name = pageName(url)): Promise<void> {
  for (const theme of THEMES) {
    await setTheme(page, theme);
    for (const viewport of WIDTHS) {
      await page.setViewportSize(viewport);
      await gotoReady(page, url);
      await page.screenshot({ path: join(DIR, `${name}-${viewport.width}-${theme}.png`), fullPage: true });
    }
  }
}

test.beforeAll(() => {
  if (DIR) mkdirSync(DIR, { recursive: true });
});

test("every signed-in page as the owner", async ({ page, request }) => {
  const workouts = await apiGet<{ items: { id: number }[] }>(request, "/v1/training/workouts", { limit: "1" });
  if (workouts.items.length === 0) {
    const { token } = await apiSession(request, OWNER);
    for (const [i, daysAgo] of OWNER_WORKOUTS_DAYS_AGO.entries()) {
      await seedWorkout(request, token, { daysAgo, kg: 60 + i * 2.5, reps: 8 });
    }
  }
  const activities = await apiGet<{ items: { id: number }[] }>(request, "/v1/activities", { limit: "1" });
  const latest = await apiGet<{ items: { id: number }[] }>(request, "/v1/training/workouts", { limit: "1" });
  const detail = [
    ...activities.items.slice(0, 1).map((a) => `/activities/${a.id}`),
    ...latest.items.slice(0, 1).map((w) => `/training/history/${w.id}`),
  ];

  await login(page);
  for (const url of [...APP_PAGES, ...detail]) {
    await test.step(url, async () => {
      await shoot(page, url);
    });
  }
  await shoot(page, NOT_FOUND_PAGE, "not-found");
});

test("empty states of Today and Progress for a fresh account", async ({ page, request }) => {
  const user = await createUser(request, "screens");
  await login(page, user);
  await shoot(page, "/", "today-empty");
  await shoot(page, "/progress", "progress-empty");
});

test("public pages", async ({ page }) => {
  for (const url of PUBLIC_PAGES) {
    await test.step(url, async () => {
      await shoot(page, url);
    });
  }
});
