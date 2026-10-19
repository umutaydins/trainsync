import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { leaveTo } from "@/features/settings/account";
import { CoachSettings } from "@/features/settings/components/coach-settings";
import { StravaCard, TelegramCard } from "@/features/settings/components/connection-cards";
import { DeleteAccountCard, ExportCard } from "@/features/settings/components/data-cards";
import { PasswordForm } from "@/features/settings/components/password-form";
import { ProfileForm } from "@/features/settings/components/profile-form";
import { SessionsList } from "@/features/settings/components/sessions-list";
import { SettingsHub } from "@/features/settings/components/settings-hub";
import type { Locale } from "@/i18n/config";
import { violations } from "./support/axe";
import { renderWithIntl } from "./support/intl";
import { MAC, me, session, settings } from "./support/settings-fixtures";

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/me" }));
vi.mock("@/features/settings/account", async (original) => ({
  ...(await original<typeof import("@/features/settings/account")>()),
  leaveTo: vi.fn(),
}));

const fetchMock = vi.fn<typeof fetch>();

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/** Writes as `METHOD url` with the parsed body (reads and coach previews left out). */
function writes(): { call: string; body: unknown }[] {
  return fetchMock.mock.calls
    .filter(([, init]) => (init?.method ?? "GET") !== "GET")
    .map(([url, init]) => ({ call: `${init?.method} ${String(url)}`, body: init?.body ? JSON.parse(String(init.body)) : null }));
}

function renderUi(ui: ReactElement, locale: Locale = "en") {
  return renderWithIntl(<ToastProvider>{ui}</ToastProvider>, locale);
}

/** Desktop: ResponsiveSheet renders a dialog (jsdom has no matchMedia). */
function stubDesktop() {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: true,
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

beforeEach(() => {
  fetchMock.mockReset();
  router.refresh.mockReset();
  vi.mocked(leaveTo).mockReset();
  fetchMock.mockImplementation(async (url) =>
    String(url).includes("coach-preview") ? json({ line: "Clean session.", savage: false }) : json({}),
  );
  vi.stubGlobal("fetch", fetchMock);
  stubDesktop();
});

describe("Me hub", () => {
  it("links every section, Admin for the owner only, set up again, legal pages and sign out", () => {
    const { unmount } = renderUi(<SettingsHub me={me()} />);
    const nav = screen.getByRole("navigation", { name: "Me" });
    expect(within(nav).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual([
      "/me/profile",
      "/me/security",
      "/me/coach",
      "/me/connections",
      "/me/data",
    ]);
    expect(screen.getByRole("link", { name: "Set up again" })).toHaveAttribute("href", "/onboarding");
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy");
    expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    expect(screen.getByRole("button", { name: "Sign out" }).closest("form")).toHaveAttribute("action", "/api/auth/logout");
    unmount();
    renderUi(<SettingsHub me={me({ role: "owner" })} />);
    expect(screen.getByRole("link", { name: /Admin/ })).toHaveAttribute("href", "/admin");
  });

  it("renders in Turkish with the Data row named like the legal pages", () => {
    renderUi(<SettingsHub me={me()} />, "tr");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Ben");
    expect(screen.getByRole("link", { name: /Veriler.*Dışa aktar · Hesabı sil/ })).toHaveAttribute("href", "/me/data");
  });
});

describe("Profile", () => {
  it("patches only the changed name and zone, then refreshes for the tz cookie", async () => {
    fetchMock.mockResolvedValue(json(me({ display_name: "Umut", timezone: "UTC" })));
    renderUi(<ProfileForm me={me()} lang="en" theme="system" />);
    const name = screen.getByLabelText("Display name");
    await userEvent.clear(name);
    await userEvent.type(name, "Umut");
    await userEvent.selectOptions(screen.getByLabelText("Time zone"), "UTC");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalledOnce());
    expect(writes()).toEqual([{ call: "PATCH /api/ts/v1/me", body: { display_name: "Umut", timezone: "UTC" } }]);
  });

  it("refuses an empty name without calling the API", async () => {
    renderUi(<ProfileForm me={me()} lang="en" theme="system" />);
    await userEvent.clear(screen.getByLabelText("Display name"));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByText(/Enter a name/)).toBeInTheDocument();
    expect(writes()).toEqual([]);
  });

  it("switches the language at once and refreshes so the UI follows", async () => {
    renderUi(<ProfileForm me={me()} lang="en" theme="dark" />);
    await userEvent.click(screen.getByRole("radio", { name: /Türkçe/ }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalledOnce());
    expect(writes()).toEqual([{ call: "PATCH /api/ts/v1/me/settings", body: { lang: "tr" } }]);
    expect(screen.getByRole("radio", { name: "Dark" })).toHaveAttribute("aria-checked", "true");
  });

  it("goes back to the old language when the save fails", async () => {
    fetchMock.mockResolvedValue(json({ error: "boom" }, 500));
    renderUi(<ProfileForm me={me()} lang="en" theme="system" />);
    await userEvent.click(screen.getByRole("radio", { name: /Türkçe/ }));
    await waitFor(() => expect(screen.getByRole("radio", { name: /English/ })).toBeChecked());
    expect(router.refresh).not.toHaveBeenCalled();
  });
});

describe("Security", () => {
  it("changes the password and says a wrong current one is wrong", async () => {
    fetchMock.mockResolvedValueOnce(json({ error: "not signed in" }, 401)).mockResolvedValueOnce(new Response(null, { status: 204 }));
    renderUi(<PasswordForm />);
    await userEvent.type(screen.getByLabelText("Current password"), "old password");
    await userEvent.type(screen.getByLabelText("New password"), "a brand new password");
    await userEvent.type(screen.getByLabelText("Repeat the new password"), "a brand new password");
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText("That is not your current password.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Change password" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalledOnce());
    expect(writes()[1]).toEqual({
      call: "POST /api/ts/v1/me/password",
      body: { current_password: "old password", new_password: "a brand new password" },
    });
    expect(screen.getByLabelText("Current password")).toHaveValue("");
  });

  it("signs out another device and keeps this one", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    renderUi(<SessionsList initial={[session(), session({ id: 13, current: false, user_agent: MAC })]} />);
    expect(screen.getByText("This device")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out Chrome · macOS" }));
    const dialog = await screen.findByRole("dialog", { name: "Sign out this device?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(screen.queryByText("Chrome · macOS")).not.toBeInTheDocument());
    expect(writes()).toEqual([{ call: "DELETE /api/ts/v1/me/sessions/13", body: null }]);
    expect(leaveTo).not.toHaveBeenCalled();
  });

  it("signing out this device ends the browser session and goes to sign-in", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    renderUi(<SessionsList initial={[session()]} />);
    await userEvent.click(screen.getByRole("button", { name: "Sign out Safari · iPhone" }));
    const dialog = await screen.findByRole("dialog", { name: "Sign out here?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(leaveTo).toHaveBeenCalledWith("/login"));
    expect(writes().map((w) => w.call)).toEqual(["DELETE /api/ts/v1/me/sessions/12", "POST /api/auth/logout"]);
  });
});

describe("Coach & reminders", () => {
  it("saves only the changed reminder fields and adopts the API's answer", async () => {
    fetchMock.mockImplementation(async (url, init) =>
      init?.method === "PATCH"
        ? json(settings({ checkin_reminder_minutes: 30, quiet_hours: "22:00-07:00", custom: ["checkin_reminder_minutes", "quiet_hours"] }))
        : json({ line: "Clean session.", savage: false }),
    );
    renderUi(<CoachSettings initial={settings()} />);
    const minutes = screen.getByLabelText("Reminder after (minutes)");
    await userEvent.clear(minutes);
    await userEvent.type(minutes, "30");
    await userEvent.clear(screen.getByLabelText("From"));
    await userEvent.type(screen.getByLabelText("From"), "22:00");
    const reminders = screen.getByRole("region", { name: "Check-in and reminders" });
    await userEvent.click(within(reminders).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toEqual({
      call: "PATCH /api/ts/v1/me/settings",
      body: { checkin_reminder_minutes: 30, quiet_hours: "22:00-07:00" },
    });
    expect(await screen.findByRole("button", { name: "Reset Quiet hours to the default" })).toBeInTheDocument();
  });

  it("refuses reminder minutes out of range", async () => {
    renderUi(<CoachSettings initial={settings()} />);
    const minutes = screen.getByLabelText("Reminder after (minutes)");
    await userEvent.clear(minutes);
    await userEvent.type(minutes, "999");
    const reminders = screen.getByRole("region", { name: "Check-in and reminders" });
    await userEvent.click(within(reminders).getByRole("button", { name: "Save" }));
    expect(screen.getByText("A whole number from 0 to 720.")).toBeInTheDocument();
    expect(writes()).toEqual([]);
  });

  it("resets a custom field with null and offers no reset for defaults", async () => {
    fetchMock.mockImplementation(async (url, init) =>
      init?.method === "PATCH" ? json(settings()) : json({ line: "Clean session.", savage: false }),
    );
    renderUi(<CoachSettings initial={settings({ sugar_limit_g: 30, country: "TR", custom: ["sugar_limit_g", "country"] })} />);
    expect(screen.queryByRole("button", { name: /Reset Check-in time/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reset Daily sugar limit (g) to the default" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toEqual({ call: "PATCH /api/ts/v1/me/settings", body: { sugar_limit_g: null } });
    await waitFor(() => expect(screen.getByLabelText("Daily sugar limit (g)")).toHaveValue("50"));
  });

  it("saves the voice and resets all of it to the default", async () => {
    fetchMock.mockImplementation(async (url, init) =>
      init?.method === "PATCH" ? json(settings({ tone: "hardcore", custom: ["tone"] })) : json({ line: "Go.", savage: false }),
    );
    renderUi(<CoachSettings initial={settings()} />);
    await userEvent.click(screen.getByRole("radio", { name: /Hardcore/ }));
    const voice = screen.getByRole("region", { name: "Coach voice" });
    await userEvent.click(within(voice).getByRole("button", { name: "Save" }));
    await userEvent.click(await screen.findByRole("button", { name: "Reset Coach voice to the default" }));
    await waitFor(() => expect(writes()).toHaveLength(2));
    expect(writes().map((w) => w.body)).toEqual([{ tone: "hardcore" }, { tone: null, intensity: null, profanity: null }]);
  });

  it("switches digests and the check-in at once", async () => {
    fetchMock.mockImplementation(async (url, init) =>
      init?.method === "PATCH" ? json(settings({ stats_digest_enabled: false })) : json({ line: "Go.", savage: false }),
    );
    renderUi(<CoachSettings initial={settings()} />);
    await userEvent.click(screen.getByRole("switch", { name: "Weekly and monthly digest" }));
    await waitFor(() => expect(writes()).toEqual([{ call: "PATCH /api/ts/v1/me/settings", body: { stats_digest_enabled: false } }]));
    await waitFor(() => expect(screen.getByRole("switch", { name: "Weekly and monthly digest" })).not.toBeChecked());
  });

  it("sends the chosen country and shows the emergency number", async () => {
    fetchMock.mockImplementation(async (url, init) =>
      init?.method === "PATCH" ? json(settings({ country: "US", emergency_number: "911", custom: ["country"] })) : json({ line: "Go.", savage: false }),
    );
    renderUi(<CoachSettings initial={settings()} />);
    expect(screen.getByText("Emergency number: 112")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Country"), "US");
    const safety = screen.getByRole("region", { name: "Safety" });
    await userEvent.click(within(safety).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Emergency number: 911")).toBeInTheDocument();
    expect(writes()[0]?.body).toEqual({ country: "US" });
  });
});

describe("Connections", () => {
  it("connects Strava back to this page and disconnects after confirming", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const { unmount } = renderUi(<StravaCard initial={{ connected: false }} returned={null} />);
    expect(screen.getByRole("link", { name: "Connect with Strava" })).toHaveAttribute(
      "href",
      "/api/strava/connect?return_to=/me/connections",
    );
    unmount();
    renderUi(<StravaCard initial={{ connected: true, connected_at: "2026-10-01T08:00:00Z" }} returned={{ connected: true }} />);
    await userEvent.click(screen.getByRole("button", { name: "Disconnect Strava" }));
    const dialog = await screen.findByRole("dialog", { name: "Disconnect Strava?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Disconnect Strava" }));
    expect(await screen.findByRole("link", { name: "Connect with Strava" })).toBeInTheDocument();
    expect(writes()).toEqual([{ call: "DELETE /api/ts/v1/me/strava", body: null }]);
  });

  it("links Telegram with a code and unlinks after confirming", async () => {
    fetchMock.mockImplementation(async (url, init) =>
      init?.method === "POST"
        ? json({ code: "K7Q2M9XD", command: "/link K7Q2M9XD", expires_at: "2026-10-19T08:10:00Z", bot_url: null })
        : init?.method === "DELETE"
          ? new Response(null, { status: 204 })
          : json({ linked: true, linked_at: "2026-10-19T08:05:00Z" }),
    );
    renderUi(<TelegramCard initial={{ linked: false }} />);
    await userEvent.click(screen.getByRole("button", { name: "Get a link code" }));
    expect(await screen.findByText("K7Q2M9XD")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "I sent it, check again" }));
    await userEvent.click(await screen.findByRole("button", { name: "Unlink Telegram" }));
    const dialog = await screen.findByRole("dialog", { name: "Unlink Telegram?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Unlink Telegram" }));
    expect(await screen.findByText("Not linked yet.")).toBeInTheDocument();
    expect(writes().map((w) => w.call)).toEqual(["POST /api/ts/v1/me/telegram/code", "DELETE /api/ts/v1/me/telegram"]);
  });
});

describe("Data", () => {
  it("downloads the export from the route handler", () => {
    renderUi(<ExportCard />);
    expect(screen.getByRole("link", { name: "Download my data" })).toHaveAttribute("href", "/api/account/export");
  });

  it("deletes only after the password and the typed word, then goes to sign-in", async () => {
    fetchMock.mockResolvedValueOnce(json({ error: "not signed in" }, 401)).mockResolvedValueOnce(new Response(null, { status: 204 }));
    renderUi(<DeleteAccountCard isOwner={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Delete my account" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete your account?" });
    const confirm = within(dialog).getByRole("button", { name: "Delete my account" });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText("Your password"), "wrong");
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText("Type DELETE to confirm"), "DELET");
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText("Type DELETE to confirm"), "E");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("That password is not right.");
    expect(leaveTo).not.toHaveBeenCalled();
    await userEvent.click(confirm);
    await waitFor(() => expect(leaveTo).toHaveBeenCalledWith("/login"));
    expect(writes()).toEqual([
      { call: "DELETE /api/account", body: { password: "wrong" } },
      { call: "DELETE /api/account", body: { password: "wrong" } },
    ]);
  });

  it("asks for SİL in Turkish and offers no deletion to the owner", async () => {
    const { unmount } = renderUi(<DeleteAccountCard isOwner={false} />, "tr");
    await userEvent.click(screen.getByRole("button", { name: "Hesabımı sil" }));
    expect(await screen.findByLabelText("Onaylamak için SİL yaz")).toBeInTheDocument();
    unmount();
    renderUi(<DeleteAccountCard isOwner />);
    expect(screen.queryByRole("button", { name: "Delete my account" })).not.toBeInTheDocument();
    expect(screen.getByText("The owner account cannot be deleted here.")).toBeInTheDocument();
  });
});

describe("Me accessibility (axe) in both languages", () => {
  const pages: [string, () => ReactElement][] = [
    ["hub", () => <SettingsHub me={me({ role: "owner" })} />],
    ["profile", () => <ProfileForm me={me()} lang="en" theme="system" />],
    ["password", () => <PasswordForm />],
    ["sessions", () => <SessionsList initial={[session(), session({ id: 13, current: false, user_agent: MAC })]} />],
    ["coach", () => <CoachSettings initial={settings({ custom: ["tone"] })} />],
    ["strava", () => <StravaCard initial={{ connected: false }} returned={{ error: "access_denied" }} />],
    ["telegram", () => <TelegramCard initial={{ linked: true, linked_at: "2026-10-19T08:05:00Z" }} />],
    ["data", () => (
      <>
        <ExportCard />
        <DeleteAccountCard isOwner={false} />
      </>
    )],
  ];
  it.each(pages.flatMap(([name, ui]) => (["en", "tr"] as const).map((locale) => [name, locale, ui] as const)))(
    "%s (%s)",
    async (_name, locale, ui) => {
      expect(await violations(<ToastProvider>{ui()}</ToastProvider>, locale)).toEqual([]);
    },
  );
});
