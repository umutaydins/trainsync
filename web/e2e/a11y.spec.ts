import { expect, test, type Page } from "@playwright/test";

import {
  APP_PAGES,
  NOT_FOUND_PAGE,
  NARROW,
  PHONE,
  PUBLIC_PAGES,
  THEMES,
  WIDE_PHONE,
  apiGet,
  expectNoAxe,
  gotoReady,
  login,
  noHorizontalScroll,
  setTheme,
} from "./support";

// Animations off: axe must not judge a colour halfway through a fade.
test.use({ reducedMotion: "reduce" });

async function checkPage(page: Page, url: string): Promise<void> {
  for (const theme of THEMES) {
    await setTheme(page, theme);
    await page.setViewportSize(PHONE);
    await gotoReady(page, url);
    await expect(page.locator("html")).toHaveClass(new RegExp(`\\b${theme}\\b`));
    await expectNoAxe(page, `${url} (${theme}, ${PHONE.width} px)`);
  }
  for (const viewport of [NARROW, WIDE_PHONE]) {
    await page.setViewportSize(viewport);
    await noHorizontalScroll(page, `${url} at ${viewport.width} px`);
  }
}

test("axe and no sideways scroll on every signed-in page, dark and light", async ({ page, request }) => {
  await login(page);
  const activities = await apiGet<{ items: { id: number }[] }>(request, "/v1/activities", { limit: "1" });
  const workouts = await apiGet<{ items: { id: number }[] }>(request, "/v1/training/workouts", { limit: "1" });
  const detail = [
    NOT_FOUND_PAGE,
    ...activities.items.slice(0, 1).map((a) => `/activities/${a.id}`),
    ...workouts.items.slice(0, 1).map((w) => `/training/history/${w.id}`),
  ];
  for (const url of [...APP_PAGES, ...detail]) {
    await test.step(url, async () => {
      await checkPage(page, url);
    });
  }
});

test("axe and no sideways scroll on every public page, dark and light", async ({ page }) => {
  for (const url of PUBLIC_PAGES) {
    await test.step(url, async () => {
      await checkPage(page, url);
    });
  }
});
