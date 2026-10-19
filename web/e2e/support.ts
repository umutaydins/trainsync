/**
 * Shared helpers for the e2e specs (P8.17): sign-in, navigation that waits for Next's streamed
 * page to settle, the API with the dev key, fresh users, axe and layout checks.
 */
import { randomUUID } from "node:crypto";

import AxeBuilder from "@axe-core/playwright";
import { expect, type APIRequestContext, type Locator, type Page } from "@playwright/test";

export const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";
export const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";
export const API_KEY = process.env.E2E_API_KEY ?? "dev-key-1";
export const OWNER = {
  email: process.env.E2E_EMAIL ?? "owner@example.com",
  password: process.env.E2E_PASSWORD ?? "dev-e2e-owner-password",
};

export const PHONE = { width: 375, height: 812 } as const;
export const DESKTOP = { width: 1280, height: 800 } as const;
export const NARROW = { width: 360, height: 780 } as const;
export const WIDE_PHONE = { width: 430, height: 932 } as const;

/** Every signed-in page (as the owner, who also sees /admin). */
export const APP_PAGES = [
  "/",
  "/training",
  "/training/programs",
  "/training/history",
  "/training/checkins",
  "/training/progress",
  "/nutrition",
  "/progress",
  "/activities",
  "/sync",
  "/me",
  "/me/profile",
  "/me/coach",
  "/me/connections",
  "/me/data",
  "/me/security",
  "/admin",
  "/onboarding",
] as const;

/** A signed-in URL that renders the not-found page (no workout has this id). */
export const NOT_FOUND_PAGE = "/training/history/2147483647";

/** Pages without a session. */
export const PUBLIC_PAGES = ["/login", "/register", "/forgot-password", "/privacy", "/terms", "/offline"] as const;

export type Theme = "dark" | "light";
export const THEMES: readonly Theme[] = ["dark", "light"];

export interface User {
  id: number;
  email: string;
  password: string;
  /** An API session token of the user (for `apiGet`/`apiPost` as them). */
  token: string;
}

/**
 * After a full page load Next streams the page: for a moment a hidden server-rendered copy sits in
 * `body > div[hidden]` beside the client's, and strict locators would see both. Wait it out. Some
 * hidden divs stay for good but hold only Suspense markers or an empty `<template>`: only one
 * with real elements in it counts. Then wait for the route's loading skeleton to go.
 */
export async function settled(page: Page): Promise<void> {
  await page.waitForLoadState("load");
  await page.waitForFunction(
    () =>
      Array.from(document.querySelectorAll("body > div[hidden]")).every((div) => div.querySelector(":not(template)") === null) &&
      // A route's loading skeleton (a labelled `Skeleton`) can still stand in for the page after "load".
      document.querySelector('.animate-pulse[role="status"]') === null,
  );
}

/** `page.goto` and wait until the streamed page has settled. */
export async function gotoReady(page: Page, url: string): Promise<void> {
  await page.goto(url);
  await settled(page);
}

/** Wait for a (full-load) navigation to `url`, e.g. the redirect after a form post, then settle. */
export async function arrived(page: Page, url: string | RegExp | ((url: URL) => boolean)): Promise<void> {
  await page.waitForURL(url);
  await settled(page);
}

/** Sign in through the form; ends on the page the app redirects to (Today by default). */
export async function login(page: Page, user: { email: string; password: string } = OWNER): Promise<void> {
  await gotoReady(page, "/login");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await arrived(page, (url) => url.pathname !== "/login");
}

/** Sign out with the button on Me (on phones it is the only one; on desktop the sidebar has one too). */
export async function logout(page: Page): Promise<void> {
  await gotoReady(page, "/me");
  await page.getByRole("button", { name: "Sign out" }).filter({ visible: true }).first().click();
  await arrived(page, /\/login/);
}

type Query = Record<string, string>;

function headers(token?: string): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : { "X-API-Key": API_KEY };
}

/** GET on the API as the owner (the dev API key), or as a user with their `token`. */
export async function apiGet<T>(request: APIRequestContext, path: string, params: Query = {}, token?: string): Promise<T> {
  const response = await request.get(`${API_URL}${path}`, { params, headers: headers(token) });
  expect(response.ok(), `GET ${path} → ${response.status()}`).toBeTruthy();
  return (await response.json()) as T;
}

/** POST on the API as the owner (the dev API key), or as a user with their `token`. */
export async function apiPost<T>(request: APIRequestContext, path: string, body: unknown = {}, token?: string): Promise<T> {
  const response = await request.post(`${API_URL}${path}`, { data: body, headers: headers(token) });
  expect(response.ok(), `POST ${path} → ${response.status()}: ${await response.text()}`).toBeTruthy();
  return (await response.json()) as T;
}

/** PUT on the API as the owner (the dev API key), or as a user with their `token`. */
export async function apiPut<T>(request: APIRequestContext, path: string, body: unknown, token?: string): Promise<T> {
  const response = await request.put(`${API_URL}${path}`, { data: body, headers: headers(token) });
  expect(response.ok(), `PUT ${path} → ${response.status()}: ${await response.text()}`).toBeTruthy();
  return (await response.json()) as T;
}

const DAY_MS = 24 * 60 * 60 * 1000;
const BACK_SQUAT = "back-squat";

/**
 * A finished free workout `daysAgo` days back with `sets` sets of back squats, through the API
 * (the same idempotent calls the workout screen makes). Returns the workout id.
 */
export async function seedWorkout(
  request: APIRequestContext,
  token: string,
  { daysAgo, kg, reps, sets = 3 }: { daysAgo: number; kg: number; reps: number; sets?: number },
): Promise<number> {
  const { items } = await apiGet<{ items: { id: number; slug: string }[] }>(request, "/v1/training/exercises", {}, token);
  const squat = items.find((e) => e.slug === BACK_SQUAT);
  if (!squat) throw new Error("the exercise library has no back squat");
  const started = new Date(Date.now() - daysAgo * DAY_MS);
  const workout = await apiPut<{ id: number }>(request, `/v1/training/workouts/${randomUUID()}`, { started_at: started.toISOString() }, token);
  for (let index = 1; index <= sets; index += 1) {
    const completed = new Date(started.getTime() + index * 3 * 60 * 1000).toISOString();
    await apiPut(
      request,
      `/v1/training/workouts/${workout.id}/sets/${randomUUID()}`,
      { exercise_id: squat.id, set_index: index, reps, weight_kg: kg, completed_at: completed },
      token,
    );
  }
  await apiPost(request, `/v1/training/workouts/${workout.id}/finish`, {}, token);
  return workout.id;
}

/** Unique per call and per run, so the specs can run again on the same database. */
export function uniqueEmail(prefix: string): string {
  return `e2e-${prefix}-${Date.now()}-${randomUUID().slice(0, 8)}@example.com`;
}

export const USER_PASSWORD = "e2e-user-password-1";

/** One fake client address per registration: the API allows a few sign-ups per address and hour. */
function fakeAddress(): Record<string, string> {
  const byte = () => Math.floor(Math.random() * 250) + 1;
  return { "X-Forwarded-For": `10.${byte()}.${byte()}.${byte()}` };
}

export interface Invite {
  code: string;
  url: string;
}

export async function createInvite(request: APIRequestContext, note = "e2e"): Promise<Invite> {
  return apiPost<Invite>(request, "/v1/admin/invites", { note });
}

/** A fresh account (owner invite → register on the API) and an API session for it. */
export async function createUser(request: APIRequestContext, prefix = "user", timezone = "Europe/Berlin"): Promise<User> {
  const invite = await createInvite(request, `e2e ${prefix}`);
  const email = uniqueEmail(prefix);
  const registered = await request.post(`${API_URL}/v1/auth/register`, {
    data: { email, password: USER_PASSWORD, invite_code: invite.code, timezone },
    headers: fakeAddress(),
  });
  expect(registered.ok(), `register → ${registered.status()}: ${await registered.text()}`).toBeTruthy();
  const { token, id } = await apiSession(request, { email, password: USER_PASSWORD });
  return { id, email, password: USER_PASSWORD, token };
}

/** Sign in on the API: a session token (and the user id) for `apiGet`/`apiPost` as that user. */
export async function apiSession(
  request: APIRequestContext,
  user: { email: string; password: string },
): Promise<{ token: string; id: number }> {
  const session = await request.post(`${API_URL}/v1/auth/login`, { data: user, headers: fakeAddress() });
  expect(session.ok(), `login → ${session.status()}`).toBeTruthy();
  const { token, user: me } = (await session.json()) as { token: string; user: { id: number } };
  return { token, id: me.id };
}

/** The theme cookie the server renders `html.<theme>` from (no flash, no JS needed). */
export async function setTheme(page: Page, theme: Theme): Promise<void> {
  await page.context().addCookies([{ name: "theme", value: theme, url: BASE_URL }]);
}

/**
 * axe-core with every rule on the current page; `what` names the page in the failure. Soft: the
 * test goes on and reports every page's violations at the end.
 */
export async function expectNoAxe(page: Page, what: string): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  const found = results.violations.map((v) => `${v.id} (${v.impact ?? "?"}): ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect.soft(found, `axe on ${what}`).toEqual([]);
}

/** The page does not scroll sideways at the current viewport (soft, like `expectNoAxe`). */
export async function noHorizontalScroll(page: Page, what = "page"): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect.soft(overflow, `${what} scrolls sideways`).toBeLessThanOrEqual(0);
}

/**
 * The toast with `text`. Never `getByText` for a toast: Radix also copies its text into a hidden
 * live region, so the text is on the page twice and a strict locator fails.
 */
export function toast(page: Page, text: string | RegExp): Locator {
  return page.getByTestId("toast").filter({ hasText: text });
}

/** The signed-in app's not-found page. */
export async function expectNotFound(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to Today" })).toBeVisible();
}
