import { screen } from "@testing-library/react";
import axe from "axe-core";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CoachPage from "@/app/(app)/me/coach/page";
import ConnectionsPage from "@/app/(app)/me/connections/page";
import DataPage from "@/app/(app)/me/data/page";
import MePage from "@/app/(app)/me/page";
import ProfilePage from "@/app/(app)/me/profile/page";
import SecurityPage from "@/app/(app)/me/security/page";
import { ToastProvider } from "@/components/ui/toast";
import { settingsApi } from "@/features/settings/api";
import { ApiError, api } from "@/lib/api";
import { renderWithIntl } from "./support/intl";
import { me, session, settings } from "./support/settings-fixtures";

const locale = vi.hoisted(() => ({ current: "en" as "en" | "tr" }));
vi.mock("next-intl/server", async () => {
  const { translatorFor } = await import("./support/intl");
  return { getTranslations: (namespace?: string) => translatorFor(locale.current)(namespace) };
});
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/me" }));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (name: string) => (name === "theme" ? { value: "light" } : undefined) }) }));

const NO_PARAMS = Promise.resolve({});

const PAGES: [string, () => Promise<ReactElement>][] = [
  ["me", () => MePage()],
  ["profile", () => ProfilePage()],
  ["security", () => SecurityPage()],
  ["coach", () => CoachPage()],
  ["connections", () => ConnectionsPage({ searchParams: NO_PARAMS })],
  ["data", () => DataPage()],
];

async function renderPage(page: () => Promise<ReactElement>, lang: "en" | "tr" = "en") {
  locale.current = lang;
  return renderWithIntl(<ToastProvider>{await page()}</ToastProvider>, lang);
}

beforeEach(() => {
  locale.current = "en";
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ line: "Go.", savage: false }))));
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }));
  vi.spyOn(api, "me").mockResolvedValue(me());
  vi.spyOn(settingsApi, "settings").mockResolvedValue(settings());
  vi.spyOn(settingsApi, "sessions").mockResolvedValue({ items: [session()] });
  vi.spyOn(settingsApi, "strava").mockResolvedValue({ connected: false });
  vi.spyOn(settingsApi, "telegram").mockResolvedValue({ linked: false });
});

describe("Me pages (P8.14)", () => {
  it("sub-pages lead back to Me and the profile starts from the theme cookie", async () => {
    await renderPage(() => ProfilePage());
    expect(screen.getByRole("link", { name: "Me" })).toHaveAttribute("href", "/me");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Profile");
    expect(screen.getByRole("radio", { name: "Light" })).toHaveAttribute("aria-checked", "true");
  });

  it("confirms a Strava connection that came back from OAuth", async () => {
    vi.mocked(settingsApi.strava).mockResolvedValue({ connected: true, connected_at: "2026-10-19T08:00:00Z" });
    await renderPage(() => ConnectionsPage({ searchParams: Promise.resolve({ connected: "1" }) }));
    expect(screen.getByRole("button", { name: "Disconnect Strava" })).toBeInTheDocument();
  });

  it("shows error states when the API fails", async () => {
    vi.mocked(settingsApi.settings).mockRejectedValue(new ApiError(502, "down"));
    vi.mocked(settingsApi.sessions).mockRejectedValue(new ApiError(502, "down"));
    vi.mocked(settingsApi.telegram).mockRejectedValue(new ApiError(502, "down"));
    const { unmount } = await renderPage(() => CoachPage());
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load your settings");
    unmount();
    const security = await renderPage(() => SecurityPage());
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load your devices");
    security.unmount();
    await renderPage(() => ConnectionsPage({ searchParams: NO_PARAMS }));
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load your Telegram connection");
  });

  it("the owner gets no delete button", async () => {
    vi.mocked(api.me).mockResolvedValue(me({ role: "owner" }));
    await renderPage(() => DataPage());
    expect(screen.getByText("The owner account cannot be deleted here.")).toBeInTheDocument();
  });

  it.each(PAGES.flatMap(([name, page]) => (["en", "tr"] as const).map((lang) => [name, lang, page] as const)))(
    "%s renders axe-clean (%s)",
    async (_name, lang, page) => {
      const { container } = await renderPage(page, lang);
      const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
      expect(result.violations.map((v) => v.id)).toEqual([]);
    },
  );
});
