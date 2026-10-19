import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingFlow } from "@/features/onboarding/components/onboarding-flow";
import { toProfile } from "@/features/nutrition/profile";
import { STEPS, initialStep, stravaReturnFrom } from "@/features/onboarding/steps";
import type { OnboardingData } from "@/features/onboarding/types";
import { renderWithIntl } from "./support/intl";

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/onboarding" }));

const fetchMock = vi.fn<typeof fetch>();

function data(overrides: Partial<OnboardingData> = {}): OnboardingData {
  return {
    timezone: "Europe/Berlin",
    settings: { lang: "en", tone: "neutral", intensity: "normal", profanity: "roast" },
    strava: { connected: false },
    telegram: { linked: false },
    profile: null,
    stravaReturn: null,
    ...overrides,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/** Every request as `METHOD url`, with the parsed body. */
function requests(): { call: string; body: unknown }[] {
  return fetchMock.mock.calls.map(([url, init]) => ({
    call: `${init?.method ?? "GET"} ${String(url)}`,
    body: init?.body ? JSON.parse(String(init.body)) : null,
  }));
}

const skip = () => userEvent.click(screen.getByRole("button", { name: "Skip" }));
const heading = () => screen.getByRole("heading", { level: 1 });

describe("onboarding (P8.13)", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    router.refresh.mockReset();
    fetchMock.mockImplementation(async (url) =>
      String(url).includes("coach-preview") ? json({ line: "Clean session.", savage: false }) : json({}),
    );
    vi.stubGlobal("fetch", fetchMock);
  });

  it("walks through every step with skip and back, then links to Today", async () => {
    renderWithIntl(<OnboardingFlow data={data()} />);
    expect(screen.getByText(`Step 1 of ${STEPS.length}`)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back" })).toBeDisabled();
    const titles = [heading().textContent];
    for (let i = 1; i < STEPS.length; i += 1) {
      await skip();
      titles.push(heading().textContent);
    }
    expect(titles).toEqual([
      "Where do you train?",
      "Pick your language.",
      "How hard should the coach push?",
      "Connect Strava.",
      "Link Telegram.",
      "Your numbers.",
      "You are set.",
    ]);
    expect(screen.queryByRole("button", { name: "Skip" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Today" })).toHaveAttribute("href", "/");
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(heading()).toHaveTextContent("Your numbers.");
    expect(requests().filter((r) => !r.call.startsWith("GET"))).toEqual([]);
  });

  it("saves the time zone and the language, then refreshes so the UI follows", async () => {
    renderWithIntl(<OnboardingFlow data={data()} />);
    await userEvent.selectOptions(screen.getByLabelText("Time zone"), "Asia/Tokyo");
    await userEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(heading()).toHaveTextContent("Pick your language."));
    await userEvent.click(screen.getByRole("radio", { name: /Türkçe/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(heading()).toHaveTextContent("How hard should the coach push?"));
    expect(requests().filter((r) => r.call.startsWith("PATCH"))).toEqual([
      { call: "PATCH /api/ts/v1/me", body: { timezone: "Asia/Tokyo" } },
      { call: "PATCH /api/ts/v1/me/settings", body: { lang: "tr" } },
    ]);
    expect(router.refresh).toHaveBeenCalledTimes(2);
  });

  it("stays on a step whose save failed and says so", async () => {
    fetchMock.mockResolvedValue(json({ error: "boom" }, 500));
    renderWithIntl(<OnboardingFlow data={data()} />);
    await userEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not save.");
    expect(heading()).toHaveTextContent("Where do you train?");
  });

  it("previews the coach for each choice and unlocks intensity and profanity in order", async () => {
    fetchMock.mockImplementation(async (url) => {
      const savage = String(url).includes("intensity=savage");
      return String(url).includes("coach-preview") ? json({ line: savage ? "Pathetic." : "Nice work.", savage }) : json({});
    });
    renderWithIntl(<OnboardingFlow data={data()} />);
    await skip();
    await skip();
    expect(await screen.findByText("“Nice work.”")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Intensity" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Hardcore/ }));
    expect(screen.queryByRole("group", { name: "Language" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Savage/ }));
    await userEvent.click(screen.getByRole("radio", { name: /Max/ }));
    expect(await screen.findByText("“Pathetic.”")).toBeInTheDocument();
    const last = requests().filter((r) => r.call.includes("coach-preview")).at(-1)?.call ?? "";
    expect(new URL(last.split(" ")[1] ?? "", "http://x").searchParams.toString()).toBe(
      "tone=hardcore&intensity=savage&profanity=max&lang=en",
    );
    await userEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(heading()).toHaveTextContent("Connect Strava."));
    expect(requests().find((r) => r.call === "PATCH /api/ts/v1/me/settings")?.body).toEqual({
      tone: "hardcore",
      intensity: "savage",
      profanity: "max",
    });
  });

  it("says when there is no preview", async () => {
    fetchMock.mockResolvedValue(json({ error: "down" }, 502));
    renderWithIntl(<OnboardingFlow data={data()} />);
    await skip();
    await skip();
    expect(await screen.findByText(/No preview right now/)).toBeInTheDocument();
  });

  it("shows the official Strava button when not connected, and resumes there after OAuth", async () => {
    renderWithIntl(<OnboardingFlow data={data({ stravaReturn: { error: "access denied" } })} />);
    expect(heading()).toHaveTextContent("Connect Strava.");
    const button = screen.getByRole("link", { name: "Connect with Strava" });
    expect(button).toHaveAttribute("href", "/api/strava/connect?return_to=/onboarding");
    expect(within(button).getByRole("img")).toHaveAttribute("src", "/strava/btn_strava_connect_with_orange.svg");
    expect(screen.getByRole("img", { name: "Powered by Strava" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Strava did not connect: access denied");
  });

  it("shows a connected Strava account and moves on", async () => {
    const connected = { connected: true, connected_at: "2026-10-19T08:00:00Z", athlete_id: 1, strava_athlete_id: 2 };
    renderWithIntl(<OnboardingFlow data={data({ strava: connected, stravaReturn: { connected: true } })} />);
    expect(screen.getByRole("status")).toHaveTextContent("Strava is connected.");
    expect(screen.queryByRole("link", { name: "Connect with Strava" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(heading()).toHaveTextContent("Link Telegram.");
  });

  it("creates a Telegram code with the bot link and checks the link status", async () => {
    const code = { code: "K7Q2M9XD", command: "/link K7Q2M9XD", bot_url: "https://t.me/trainsync_bot?start=K7Q2M9XD", expires_at: "2026-10-19T08:10:00Z" };
    fetchMock.mockImplementation(async (url, init) => {
      if (String(url).endsWith("/telegram/code")) return json(code);
      if (String(url).endsWith("/v1/me/telegram") && !init?.method) return json({ linked: true, linked_at: "2026-10-19T08:05:00Z" });
      return json({});
    });
    renderWithIntl(<OnboardingFlow data={data({ stravaReturn: { connected: true } })} />);
    await skip();
    expect(screen.getByRole("status")).toHaveTextContent("Not linked yet.");
    await userEvent.click(screen.getByRole("button", { name: "Get a link code" }));
    expect(await screen.findByText("K7Q2M9XD")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the bot" })).toHaveAttribute("href", code.bot_url);
    expect(screen.getByText("/link K7Q2M9XD")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "I sent it, check again" }));
    expect(await screen.findByText("Telegram is linked.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(heading()).toHaveTextContent("Your numbers.");
  });

  it("checks the nutrition profile before it saves it", async () => {
    renderWithIntl(<OnboardingFlow data={data({ stravaReturn: { connected: true } })} />);
    await skip();
    await skip();
    await userEvent.type(screen.getByLabelText("Birth year"), "1850");
    await userEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    expect(screen.getByText("Enter a year from 1900 to 2100.")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Birth year"));
    await userEvent.type(screen.getByLabelText("Birth year"), "1991");
    await userEvent.type(screen.getByLabelText("Height (cm)"), "180");
    await userEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    await waitFor(() => expect(heading()).toHaveTextContent("You are set."));
    expect(requests().find((r) => r.call === "PUT /api/ts/v1/nutrition/profile")?.body).toEqual({
      sex: "male",
      birth_year: 1991,
      height_cm: 180,
      activity_baseline: "light",
      kcal_target: null,
      protein_target_g: null,
    });
  });

  it("speaks Turkish", () => {
    renderWithIntl(<OnboardingFlow data={data()} />, "tr");
    expect(heading()).toHaveTextContent("Nerede antrenman yapıyorsun?");
    expect(screen.getByRole("button", { name: "Kaydet ve devam et" })).toBeInTheDocument();
  });

  it.each([
    ["timezone", 0],
    ["language", 1],
    ["coach", 2],
    ["strava", 3],
    ["telegram", 4],
    ["profile", 5],
    ["done", 6],
  ] as const)("the %s step has no axe violations", async (_step, clicks) => {
    const { container } = renderWithIntl(
      <main>
        <OnboardingFlow data={data()} />
      </main>,
    );
    for (let i = 0; i < clicks; i += 1) await skip();
    const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });
});

describe("onboarding helpers", () => {
  it("reads the OAuth return and starts at the Strava step after it", () => {
    expect(stravaReturnFrom({ connected: "1" })).toEqual({ connected: true });
    expect(stravaReturnFrom({ connect_error: "denied" })).toEqual({ error: "denied" });
    expect(stravaReturnFrom({})).toBeNull();
    expect(STEPS[initialStep({ connected: true })]).toBe("strava");
    expect(initialStep(null)).toBe(0);
  });

  it("validates the profile against the API's bounds", () => {
    const base = { sex: "female" as const, birthYear: "1990", height: "170,5", baseline: "moderate" as const, kcalTarget: "", proteinTarget: "120" };
    expect(toProfile(base)).toEqual({
      ok: true,
      body: { sex: "female", birth_year: 1990, height_cm: 170.5, activity_baseline: "moderate", kcal_target: null, protein_target_g: 120 },
    });
    expect(toProfile({ ...base, height: "90" })).toEqual({ ok: false, field: "height" });
    expect(toProfile({ ...base, kcalTarget: "1.5" })).toEqual({ ok: false, field: "kcalTarget" });
  });
});
