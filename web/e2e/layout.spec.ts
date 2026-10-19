import { expect, test, type Page } from "@playwright/test";

import { BASE_URL, DESKTOP, gotoReady, login } from "./support";

/**
 * Layout checks from the UI review: no clipped period switcher on phones, hero text clear of the
 * stripes, full-height side panels, the tab bar never over content, cards at their own height.
 * Each check also attaches a screenshot of what it measured.
 */

const PHONE_WIDTHS = [360, 375, 390, 414, 430] as const;
const HERO_WIDTHS = [360, 414, 768, 1024, 1280, 1440, 1920] as const;
const LOCALES = ["en", "tr"] as const;
/** Sub-pixel rounding of boxes. */
const SLACK_PX = 1;

async function setLocale(page: Page, locale: (typeof LOCALES)[number]): Promise<void> {
  await page.context().addCookies([{ name: "lang", value: locale, url: BASE_URL }]);
}

async function attach(page: Page, name: string, locator = page.locator("body")): Promise<void> {
  await test.info().attach(name, { body: await locator.screenshot(), contentType: "image/png" });
}

test.describe("signed in", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test.afterEach(async ({ page }) => {
    await setLocale(page, "en");
  });

  test("period switcher: every option whole and the chosen one in view, 360–430 px", async ({ page }) => {
    for (const locale of LOCALES) {
      await setLocale(page, locale);
      for (const width of PHONE_WIDTHS) {
        await test.step(`${locale} ${width}px`, async () => {
          await page.setViewportSize({ width, height: 800 });
          await gotoReady(page, "/progress?period=all");
          const group = page.getByTestId("period-switcher").getByRole("radiogroup");
          const report = await group.evaluate((root) => {
            const box = root.getBoundingClientRect();
            const items = [...root.querySelectorAll<HTMLElement>("button")];
            return {
              overflow: root.scrollWidth - root.clientWidth,
              items: items.map((item) => {
                const rect = item.getBoundingClientRect();
                return {
                  name: item.getAttribute("aria-label") ?? item.textContent ?? "",
                  on: item.dataset.state === "on",
                  inside: rect.left >= box.left - 1 && rect.right <= box.right + 1,
                  textClipped: item.scrollWidth > item.clientWidth + 1,
                };
              }),
            };
          });
          await attach(page, `period-switcher-${locale}-${width}`, page.getByTestId("period-switcher"));
          expect(report.overflow, "the switcher scrolls: an option is cut off").toBeLessThanOrEqual(0);
          expect(report.items.filter((i) => !i.inside).map((i) => i.name), "options outside the switcher").toEqual([]);
          expect(report.items.filter((i) => i.textClipped).map((i) => i.name), "labels cut off").toEqual([]);
          expect(report.items.find((i) => i.on)?.inside).toBe(true);
        });
      }
    }
  });

  test("desktop sidebar runs the full page height and its content stays in view", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await gotoReady(page, "/progress?period=year");
    const sidebar = page.getByTestId("sidebar");
    const { aside, document: height } = await sidebar.evaluate((el) => ({
      aside: el.getBoundingClientRect().height,
      document: document.documentElement.scrollHeight,
    }));
    expect(height, "a long page").toBeGreaterThan(DESKTOP.height);
    expect(aside).toBeGreaterThanOrEqual(height - SLACK_PX);
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await expect(sidebar.getByRole("button", { name: "Sign out" })).toBeInViewport();
    await expect(sidebar.getByTestId("sidebar-name")).toBeInViewport();
  });

  test("bottom tab bar never covers the end of a page", async ({ page }) => {
    for (const width of [360, 430] as const) {
      await page.setViewportSize({ width, height: 740 });
      for (const url of ["/sync", "/progress", "/me", "/activities"]) {
        await test.step(`${url} ${width}px`, async () => {
          await gotoReady(page, url);
          await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
          const { contentBottom, barTop } = await page.evaluate(() => {
            const main = document.querySelector("main");
            const bar = [...document.querySelectorAll("nav")].find((nav) => getComputedStyle(nav).position === "fixed");
            const bottoms = [...(main?.querySelectorAll("*") ?? [])]
              .filter((el) => getComputedStyle(el).position !== "fixed" && el.getClientRects().length > 0)
              .map((el) => el.getBoundingClientRect().bottom);
            return { contentBottom: Math.max(...bottoms), barTop: bar?.getBoundingClientRect().top ?? Infinity };
          });
          await attach(page, `tabbar-${url.slice(1)}-${width}`, page.locator("html"));
          expect(contentBottom, `${url}: content under the tab bar`).toBeLessThanOrEqual(barTop + SLACK_PX);
        });
      }
    }
  });

  test("progress cards keep their natural height; swim pace is realistic", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await gotoReady(page, "/progress?period=year");
    const gaps = await page.getByTestId("progress-blocks").evaluate((root) =>
      [...root.querySelectorAll<HTMLElement>(":scope > [data-block]")].map((card) => {
        const last = card.lastElementChild?.getBoundingClientRect().bottom ?? 0;
        const padding = parseFloat(getComputedStyle(card).paddingBottom);
        return { block: card.dataset.block, empty: card.getBoundingClientRect().bottom - padding - last };
      }),
    );
    await attach(page, "progress-desktop", page.getByTestId("progress"));
    expect(gaps.length).toBeGreaterThan(3);
    expect(gaps.filter((g) => g.empty > 2), "cards stretched with empty space").toEqual([]);

    // The fake Strava seeds swims at 1:50–2:40 /100 m; the year's average lands in between.
    const swim = page.locator('[data-group="swim"]');
    if ((await swim.count()) > 0) {
      const pace = (await swim.getByText(/^\d+:\d\d$/).first().textContent()) ?? "";
      const [minutes = 0, seconds = 0] = pace.split(":").map(Number);
      const perHundred = minutes * 60 + seconds;
      expect(perHundred, `swim pace ${pace} /100 m`).toBeGreaterThanOrEqual(100);
      expect(perHundred, `swim pace ${pace} /100 m`).toBeLessThanOrEqual(170);
    }
  });
});

test("auth hero: text clear of the stripes at every width, panel as tall as the page", async ({ page }) => {
  for (const url of ["/login", "/privacy"]) {
    for (const width of HERO_WIDTHS) {
      await test.step(`${url} ${width}px`, async () => {
        await page.setViewportSize({ width, height: 800 });
        await gotoReady(page, url);
        const report = await page.evaluate(() => {
          const stripes = document.querySelector('[data-testid="auth-stripes"]')?.getBoundingClientRect();
          const text = document.querySelector('[data-testid="auth-hero-text"]');
          const range = document.createRange();
          let right = 0;
          for (const p of text?.querySelectorAll("p") ?? []) {
            if (getComputedStyle(p).display === "none") continue;
            range.selectNodeContents(p);
            for (const rect of range.getClientRects()) right = Math.max(right, rect.right);
          }
          return {
            textRight: right,
            stripesLeft: stripes?.left ?? 0,
            hero: document.querySelector('[data-testid="auth-hero"]')?.getBoundingClientRect().height ?? 0,
            page: document.documentElement.scrollHeight,
          };
        });
        await attach(page, `hero-${url.slice(1)}-${width}`, page.getByTestId("auth-hero"));
        expect(report.textRight, "hero text runs into the stripes").toBeLessThanOrEqual(report.stripesLeft);
        if (width >= 1024) expect(report.hero, "hero panel stops short of the page end").toBeGreaterThanOrEqual(report.page - SLACK_PX);
      });
    }
  }
});
