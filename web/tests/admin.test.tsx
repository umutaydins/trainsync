import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminPage from "@/app/(app)/admin/page";
import { ToastProvider } from "@/components/ui/toast";
import { adminApi } from "@/features/admin/api";
import { InvitesPanel } from "@/features/admin/components/invites-panel";
import { UsersPanel } from "@/features/admin/components/users-panel";
import { ApiError, api } from "@/lib/api";
import { violations } from "./support/axe";
import { renderWithIntl } from "./support/intl";
import { adminUser, createdInvite, invite, me } from "./support/settings-fixtures";

const locale = vi.hoisted(() => ({ current: "en" as "en" | "tr" }));
const NOT_FOUND = "NEXT_NOT_FOUND";
vi.mock("next-intl/server", async () => {
  const { translatorFor } = await import("./support/intl");
  return { getTranslations: (namespace?: string) => translatorFor(locale.current)(namespace) };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/admin",
  notFound: () => {
    throw new Error(NOT_FOUND);
  },
}));

const fetchMock = vi.fn<typeof fetch>();
const clipboard = { writeText: vi.fn(async () => undefined) };

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function writes(): string[] {
  return fetchMock.mock.calls.map(([url, init]) => `${init?.method ?? "GET"} ${String(url)} ${init?.body ?? ""}`.trim());
}

beforeEach(() => {
  locale.current = "en";
  fetchMock.mockReset();
  clipboard.writeText.mockClear();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener: () => undefined, removeEventListener: () => undefined }));
  Object.defineProperty(navigator, "clipboard", { value: clipboard, configurable: true });
});

describe("/admin page", () => {
  it("is not found for everyone but the owner, and reads nothing else for them", async () => {
    vi.spyOn(api, "me").mockResolvedValue(me({ role: "user" }));
    const invites = vi.spyOn(adminApi, "invites");
    await expect(AdminPage()).rejects.toThrow(NOT_FOUND);
    expect(invites).not.toHaveBeenCalled();
  });

  it("shows the owner the invites and the accounts, in Turkish too", async () => {
    vi.spyOn(api, "me").mockResolvedValue(me({ role: "owner" }));
    vi.spyOn(adminApi, "invites").mockResolvedValue({ items: [invite()] });
    vi.spyOn(adminApi, "users").mockResolvedValue({ items: [adminUser()] });
    locale.current = "tr";
    renderWithIntl(<ToastProvider>{await AdminPage()}</ToastProvider>, "tr");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Yönetim");
    expect(screen.getByRole("region", { name: "Davetler" })).toHaveTextContent("Aktif");
    expect(screen.getByRole("region", { name: "Hesaplar" })).toHaveTextContent("runner@example.com");
  });

  it("shows error states when the API fails", async () => {
    vi.spyOn(api, "me").mockRejectedValue(new ApiError(502, "trainsync API unavailable"));
    renderWithIntl(await AdminPage());
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load the admin page");
    vi.mocked(api.me).mockResolvedValue(me({ role: "owner" }));
    vi.spyOn(adminApi, "invites").mockRejectedValue(new ApiError(500, "boom"));
    vi.spyOn(adminApi, "users").mockResolvedValue({ items: [] });
    renderWithIntl(<ToastProvider>{await AdminPage()}</ToastProvider>);
    expect(screen.getByText("Could not load the invites")).toBeInTheDocument();
    expect(screen.getByText("No accounts")).toBeInTheDocument();
  });
});

describe("invites", () => {
  it("creates an invite with a note and shows its link once, with copy", async () => {
    fetchMock.mockResolvedValueOnce(json(createdInvite(), 201));
    renderWithIntl(
      <ToastProvider>
        <InvitesPanel initial={[]} />
      </ToastProvider>,
    );
    expect(screen.getByText("No invites yet")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Note (optional)"), "Ayşe");
    await userEvent.click(screen.getByRole("button", { name: "Create invite" }));
    const dialog = await screen.findByRole("dialog", { name: "Invite created" });
    expect(within(dialog).getByLabelText("Invite link")).toHaveValue("http://localhost:3000/register?invite=Xr2abc");
    await userEvent.click(within(dialog).getByRole("button", { name: "Copy" }));
    expect(clipboard.writeText).toHaveBeenCalledWith("http://localhost:3000/register?invite=Xr2abc");
    await userEvent.click(within(dialog).getByRole("button", { name: "Done" }));
    expect(screen.queryByText("http://localhost:3000/register?invite=Xr2abc")).not.toBeInTheDocument();
    expect(screen.getByText("Ayşe")).toBeInTheDocument();
    expect(writes()).toEqual(['POST /api/ts/v1/admin/invites {"note":"Ayşe"}']);
  });

  it("sends null without a note", async () => {
    fetchMock.mockResolvedValueOnce(json(createdInvite({ note: null }), 201));
    renderWithIntl(
      <ToastProvider>
        <InvitesPanel initial={[]} />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Create invite" }));
    await screen.findByRole("dialog", { name: "Invite created" });
    expect(writes()).toEqual(['POST /api/ts/v1/admin/invites {"note":null}']);
  });

  it("shows each status and revokes an open invite after confirming", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    renderWithIntl(
      <ToastProvider>
        <InvitesPanel
          initial={[
            invite(),
            invite({ id: 5, note: null, status: "used", used_at: "2026-10-20T08:00:00Z" }),
            invite({ id: 6, note: "old", status: "expired" }),
          ]}
        />
      </ToastProvider>,
    );
    expect(screen.getByText("Used")).toBeInTheDocument();
    expect(screen.getByText("Expired")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Revoke the invite/ })).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Revoke the invite for my training partner" }));
    const dialog = await screen.findByRole("dialog", { name: "Revoke this invite?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(screen.getByText("Revoked")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Revoke the invite/ })).not.toBeInTheDocument();
    expect(writes()).toEqual(["DELETE /api/ts/v1/admin/invites/3"]);
  });
});

describe("accounts", () => {
  it("generates a reset link and shows it once with copy", async () => {
    fetchMock.mockResolvedValueOnce(
      json({ url: "http://localhost:3000/reset-password?token=Zt4", expires_at: "2026-10-19T09:00:00Z" }),
    );
    renderWithIntl(
      <ToastProvider>
        <UsersPanel users={[adminUser({ id: 1, role: "owner", display_name: "Umut" }), adminUser()]} />
      </ToastProvider>,
    );
    expect(screen.getByText("Owner")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Password reset link for Runner" }));
    const dialog = await screen.findByRole("dialog", { name: "Reset link for Runner" });
    expect(within(dialog).getByLabelText("Reset link")).toHaveValue("http://localhost:3000/reset-password?token=Zt4");
    await userEvent.click(within(dialog).getByRole("button", { name: "Copy" }));
    expect(clipboard.writeText).toHaveBeenCalledWith("http://localhost:3000/reset-password?token=Zt4");
    expect(writes()).toEqual(["POST /api/ts/v1/admin/users/2/reset-link"]);
  });
});

describe("admin accessibility (axe)", () => {
  it.each(["en", "tr"] as const)("panels (%s)", async (lang) => {
    const ui = (
      <ToastProvider>
        <InvitesPanel initial={[invite(), invite({ id: 5, status: "revoked", revoked_at: "2026-10-20T08:00:00Z" })]} />
        <UsersPanel users={[adminUser()]} />
      </ToastProvider>
    );
    expect(await violations(ui, lang)).toEqual([]);
  });
});
