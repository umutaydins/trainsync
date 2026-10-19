import { expect, test } from "@playwright/test";

import type { WorkoutDetail } from "@/features/training/types";

import {
  PHONE,
  USER_PASSWORD,
  arrived,
  createInvite,
  gotoReady,
  login,
  logout,
  settled,
  uniqueEmail,
} from "./support";

const ZONE = "Europe/Istanbul";
const KG = 40;
const REPS = 10;

test("invite → register → onboarding → Today → a workout → sign out → sign in → the workout in history", async ({ page, request }) => {
  await page.setViewportSize(PHONE);
  const email = uniqueEmail("accounts");
  const invite = await createInvite(request, "e2e accounts");
  // The API builds the link the owner shares: /register?invite=<code>.
  expect(invite.url).toBe(`/register?invite=${invite.code}`);

  await test.step("the invite link opens the register form with the code filled in", async () => {
    await gotoReady(page, invite.url);
    await expect(page.getByRole("heading", { name: "You are invited." })).toBeVisible();
    await expect(page.getByLabel("Invite code")).toHaveValue(invite.code);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(USER_PASSWORD);
    await page.getByLabel("Display name").fill("Rookie");
    await page.getByRole("button", { name: "Create account" }).click();
    await arrived(page, /\/onboarding$/);
  });

  await test.step("onboarding: time zone, language, coach with a preview line", async () => {
    await expect(page.getByText("Step 1 of 7")).toBeVisible();
    await page.getByLabel("Time zone").selectOption(ZONE);
    await page.getByRole("button", { name: "Save and continue" }).click();

    await expect(page.getByRole("heading", { name: "Pick your language." })).toBeVisible();
    await expect(page.getByRole("radio", { name: /English/ })).toBeChecked();
    await page.getByRole("button", { name: "Save and continue" }).click();

    await expect(page.getByRole("heading", { name: "How hard should the coach push?" })).toBeVisible();
    await page.getByText("Hardcore", { exact: true }).click();
    await expect(page.getByRole("group", { name: "Intensity" })).toBeVisible();
    const preview = page.getByRole("region", { name: "How it sounds" });
    await expect(preview.getByText(/^“.+”$/)).toBeVisible();
    await page.getByRole("button", { name: "Save and continue" }).click();
  });

  await test.step("onboarding: skip Strava and Telegram, fill the body numbers, done", async () => {
    await expect(page.getByRole("heading", { name: "Connect Strava." })).toBeVisible();
    await page.getByRole("button", { name: "Skip" }).click();
    await expect(page.getByRole("heading", { name: "Link Telegram." })).toBeVisible();
    await page.getByRole("button", { name: "Skip" }).click();

    await expect(page.getByRole("heading", { name: "Your numbers." })).toBeVisible();
    await page.getByLabel("Sex (for the equation)").selectOption("female");
    await page.getByLabel("Birth year").fill("1994");
    await page.getByLabel("Height (cm)").fill("168");
    await page.getByLabel("Daily kcal target (optional)").fill("2100");
    await page.getByRole("button", { name: "Save and continue" }).click();

    await expect(page.getByRole("heading", { name: "You are set." })).toBeVisible();
    await page.getByRole("link", { name: "Go to Today" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Rookie");
  });

  await test.step("the choices were saved", async () => {
    const zone = (await page.context().cookies()).find((c) => c.name === "tz")?.value;
    expect(decodeURIComponent(zone ?? "")).toBe(ZONE);
    expect((await page.context().cookies()).find((c) => c.name === "lang")?.value).toBe("en");
  });

  let workoutId = 0;
  await test.step("an empty workout: add an exercise, log one set, finish", async () => {
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Workout" }).click();
    await expect(page).toHaveURL(/\/training$/);
    await expect(page.getByText("No program is active")).toBeVisible();
    await page.getByRole("button", { name: "Start an empty workout" }).click();
    await page.waitForURL(/\/training\/workout\/\d+$/);
    workoutId = Number(new URL(page.url()).pathname.split("/").pop());
    await expect(page.getByText("No exercises yet. Add one below.")).toBeVisible();

    await page.getByRole("button", { name: "Add exercise" }).click();
    const picker = page.getByRole("dialog", { name: "Add exercise" });
    await picker.getByLabel("Find an exercise").fill("squat");
    const choice = picker.getByRole("list", { name: "Exercises" }).getByRole("button").first();
    const name = ((await choice.locator("span").first().textContent()) ?? "").trim();
    await choice.click();
    await expect(picker).toBeHidden();

    const card = page.locator("[data-exercise-id]");
    await expect(card.getByRole("heading", { level: 2 })).toHaveText(name);
    await card.getByRole("textbox", { name: `Weight in kg, ${name} set 1`, exact: true }).fill(String(KG));
    await card.getByRole("textbox", { name: `Reps, ${name} set 1`, exact: true }).fill(String(REPS));
    await card.getByRole("button", { name: `Set done, ${name} set 1`, exact: true }).click();
    await expect(card.getByTestId("set-row").first()).toHaveAttribute("data-status", "saved");
    await page.getByRole("dialog", { name: "Rest" }).getByRole("button", { name: "Skip" }).click();

    await page.getByRole("button", { name: "Finish workout" }).click();
    await expect(page.getByTestId("workout-done")).toHaveText("Workout done.");
    await expect(page.getByTestId("workout-summary")).toHaveAttribute("data-volume", String(KG * REPS));
  });

  await test.step("sign out, sign in again; the workout is in the history", async () => {
    await logout(page);
    await gotoReady(page, "/training/history");
    await expect(page).toHaveURL(/\/login/);

    await login(page, { email, password: USER_PASSWORD });
    await gotoReady(page, "/training/history");
    const row = page.locator(`li[data-workout-id="${workoutId}"]`);
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute("data-volume", String(KG * REPS));
    await row.getByRole("link").first().click();
    await expect(page).toHaveURL(new RegExp(`/training/history/${workoutId}$`));
    await settled(page);
    await expect(page.getByTestId("workout-summary")).toHaveAttribute("data-volume", String(KG * REPS));
  });

  await test.step("the API has the finished workout with its one set (read through the BFF as this user)", async () => {
    const response = await page.request.get(`/api/ts/v1/training/workouts/${workoutId}`);
    expect(response.status()).toBe(200);
    const workout = (await response.json()) as WorkoutDetail;
    expect(workout.sets).toHaveLength(1);
    expect(workout.ended_at).not.toBeNull();
  });
});
