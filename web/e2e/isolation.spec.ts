import { expect, test } from "@playwright/test";

import { DESKTOP, PHONE, apiGet, createUser, expectNotFound, gotoReady, login, seedWorkout } from "./support";

interface ActivityPage {
  items: { id: number }[];
}

test("another user's workout and activity ids give the not-found page", async ({ page, request }) => {
  const a = await createUser(request, "isolation-a");
  const b = await createUser(request, "isolation-b");
  const workoutId = await seedWorkout(request, a.token, { daysAgo: 1, kg: 50, reps: 5 });
  // A's own workout is there for A (the id is real, not just unknown).
  await apiGet(request, `/v1/training/workouts/${workoutId}`, {}, a.token);

  await login(page, b);
  for (const url of [`/training/history/${workoutId}`, `/training/workout/${workoutId}`]) {
    await test.step(url, async () => {
      await gotoReady(page, url);
      await expectNotFound(page);
      await expect(page.getByTestId("workout-summary")).toHaveCount(0);
      await expect(page.getByTestId("workout-screen")).toHaveCount(0);
    });
  }

  await test.step("an activity of the owner", async () => {
    const owned = await apiGet<ActivityPage>(request, "/v1/activities", { limit: "1" });
    const activity = owned.items[0];
    // The owner has activities once Strava synced (dashboard.spec); otherwise there is no id to try.
    test.skip(!activity, "the owner has no synced activities yet");
    await gotoReady(page, `/activities/${activity?.id}`);
    await expectNotFound(page);
    await expect(page.getByTestId("activity-detail")).toHaveCount(0);
  });
});

test("Admin is the owner's only: hidden for a user, /admin not found; the owner sees it", async ({ page, request }) => {
  const user = await createUser(request, "isolation-user");
  await login(page, user);

  await test.step("a user: no Admin in the sidebar (desktop) or the tab bar (phone), /admin not found", async () => {
    await page.setViewportSize(DESKTOP);
    await gotoReady(page, "/");
    const sidebar = page.getByRole("complementary").getByRole("navigation", { name: "Main" });
    await expect(sidebar.getByRole("link", { name: "Sync" })).toBeVisible();
    await expect(sidebar.getByRole("link", { name: "Admin" })).toHaveCount(0);

    await page.setViewportSize(PHONE);
    const tabs = page.getByRole("navigation", { name: "Main" }).filter({ visible: true });
    await expect(tabs.getByRole("link", { name: "Me" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0);

    await gotoReady(page, "/admin");
    await expectNotFound(page);
    await expect(page.getByRole("heading", { name: "Invites" })).toHaveCount(0);
  });

  await test.step("the owner: Admin in the sidebar, the page opens", async () => {
    await page.context().clearCookies();
    await page.setViewportSize(DESKTOP);
    await login(page);
    const sidebar = page.getByRole("complementary").getByRole("navigation", { name: "Main" });
    await sidebar.getByRole("link", { name: "Admin" }).click();
    await expect(page).toHaveURL(/\/admin$/);
    await expect(page.getByRole("heading", { level: 1, name: "Admin" })).toBeVisible();
  });
});
