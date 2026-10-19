import { expect, test } from "@playwright/test";

import { BASE_URL, PHONE, apiGet, createUser, gotoReady, login, settled, toast } from "./support";

interface VoiceSettings {
  tone: string;
  lang: string;
}

const SECOND_BROWSER = "E2E-Second-Browser/1.0";

test("settings: language, theme, coach voice, sign out another device", async ({ page, request, browser }) => {
  const user = await createUser(request, "settings");
  await page.setViewportSize(PHONE);
  await login(page, user);
  const tabs = page.getByRole("navigation", { name: /Main|Ana menü/ }).filter({ visible: true });

  await test.step("Turkish on Me → Profile switches the whole UI, English switches it back", async () => {
    await gotoReady(page, "/me/profile");
    await expect(tabs.getByRole("link", { name: "Today" })).toBeVisible();
    await page.getByText("Türkçe", { exact: true }).click();
    await expect(tabs.getByRole("link", { name: "Bugün" })).toBeVisible();
    await expect(tabs.getByRole("link", { name: "Antrenman" })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "tr");
    expect((await apiGet<VoiceSettings>(request, "/v1/me/settings", {}, user.token)).lang).toBe("tr");

    // Still Turkish after a full reload (the `lang` cookie), then back to English.
    await page.reload();
    await settled(page);
    await expect(tabs.getByRole("link", { name: "Bugün" })).toBeVisible();
    await page.getByText("English", { exact: true }).click();
    await expect(tabs.getByRole("link", { name: "Today" })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
  });

  await test.step("theme: light at once, and still light after a reload", async () => {
    await page.getByRole("radio", { name: "Light" }).click();
    await expect(page.locator("html")).toHaveClass(/\blight\b/);
    await page.getByRole("radio", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveClass(/\bdark\b/);
    await page.getByRole("radio", { name: "Light" }).click();
    await page.reload();
    await settled(page);
    await expect(page.locator("html")).toHaveClass(/\blight\b/);
    await expect(page.getByRole("radio", { name: "Light" })).toHaveAttribute("aria-checked", "true");
  });

  await test.step("coach voice: hardcore is saved and survives a reload", async () => {
    await gotoReady(page, "/me/coach");
    const voice = page.getByRole("region", { name: "Coach voice" });
    await expect(voice.getByRole("radio", { name: /Neutral/ })).toBeChecked();
    await voice.getByText("Hardcore", { exact: true }).click();
    await voice.getByRole("button", { name: "Save", exact: true }).click();
    await expect(toast(page, "Saved")).toBeVisible();
    await page.reload();
    await settled(page);
    await expect(page.getByRole("region", { name: "Coach voice" }).getByRole("radio", { name: /Hardcore/ })).toBeChecked();
    expect((await apiGet<VoiceSettings>(request, "/v1/me/settings", {}, user.token)).tone).toBe("hardcore");
  });

  await test.step("a second browser signs in; this one signs it out", async () => {
    const other = await browser.newContext({ baseURL: BASE_URL, userAgent: SECOND_BROWSER });
    const second = await other.newPage();
    await login(second, user);

    await gotoReady(page, "/me/security");
    const devices = page.getByRole("region", { name: "Signed-in devices" });
    const row = devices.getByRole("listitem").filter({ hasText: SECOND_BROWSER });
    await expect(row).toHaveCount(1);
    await row.getByRole("button", { name: /^Sign out/ }).click();
    const confirm = page.getByRole("dialog", { name: "Sign out this device?" });
    await confirm.getByRole("button", { name: "Sign out" }).click();
    await expect(toast(page, "Device signed out")).toBeVisible();
    await expect(row).toHaveCount(0);
    await expect(devices.getByText("This device")).toBeVisible();

    // The second browser's session is gone: its next page load asks for a sign-in.
    await gotoReady(second, "/me");
    await expect(second).toHaveURL(/\/login/);
    await other.close();
  });
});
