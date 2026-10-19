import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Registration } from "@/features/auth/components/register-form";
import { loginError, registerErrors, resetError } from "@/features/auth/errors";
import { violations } from "./support/axe";
import { renderWithIntl } from "./support/intl";

const PASSWORD = "correct horse battery";

function answer(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

async function fill(withInvite = true) {
  await userEvent.type(screen.getByLabelText("Email"), "runner@example.com");
  await userEvent.type(screen.getByLabelText("Password"), PASSWORD);
  await userEvent.type(screen.getByLabelText("Display name"), "Runner");
  if (withInvite) await userEvent.type(screen.getByLabelText("Invite code"), "INV1");
  await userEvent.click(screen.getByRole("button", { name: "Create account" }));
}

describe("register page modes (P8.13)", () => {
  it("invite mode asks for the code, prefilled from an invite link, and posts it with the browser's zone", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(answer(409, { error: "taken" }));
    vi.stubGlobal("fetch", fetchMock);
    renderWithIntl(<Registration mode="invite" inviteCode="XYZ" />);
    const code = screen.getByLabelText("Invite code");
    expect(code).toBeRequired();
    expect(code).toHaveValue("XYZ");
    await userEvent.type(screen.getByLabelText("Email"), "runner@example.com");
    await userEvent.type(screen.getByLabelText("Password"), PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/auth/register");
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    expect(body).toMatchObject({ email: "runner@example.com", password: PASSWORD, invite_code: "XYZ", next: "/onboarding" });
    expect(body.timezone).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
    expect(await screen.findByText("An account with this email already exists. Sign in instead.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
  });

  it("open mode has no invite field and shows an invite refusal on the form", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(answer(400, { error: "invite" })));
    renderWithIntl(<Registration mode="open" />);
    expect(screen.queryByLabelText("Invite code")).not.toBeInTheDocument();
    await fill(false);
    expect(await screen.findByRole("alert")).toHaveTextContent("This invite code is missing, used or expired.");
  });

  it("closed mode shows a notice instead of the form", () => {
    renderWithIntl(<Registration mode="closed" />, "tr");
    expect(screen.getByText("Kayıtlar kapalı")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hesabı oluştur" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Giriş yap" })).toHaveAttribute("href", "/login");
  });

  it("an unknown mode says so", () => {
    renderWithIntl(<Registration mode={null} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not check whether sign-ups are open");
  });

  it("puts the invite and limit errors where they belong", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(answer(400, { error: "invite" }))
      .mockResolvedValueOnce(answer(429, { error: "too many" }));
    vi.stubGlobal("fetch", fetchMock);
    renderWithIntl(<Registration mode="invite" />);
    await fill();
    expect(await screen.findByText(/This invite code is missing/)).toBeInTheDocument();
    expect(screen.getByLabelText("Invite code")).toHaveAttribute("aria-invalid", "true");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts.");
  });

  it.each([
    ["invite", <Registration key="i" mode="invite" inviteCode="XYZ" />],
    ["open", <Registration key="o" mode="open" />],
    ["closed", <Registration key="c" mode="closed" />],
  ])("%s mode has no axe violations", async (_name, ui) => {
    expect(await violations(ui)).toEqual([]);
  });
});

describe("auth error mapping", () => {
  it("maps the API's register refusals to fields or the form", () => {
    expect(registerErrors(409)).toEqual({ form: null, fields: { email: "emailTaken" } });
    expect(registerErrors(400)).toEqual({ form: null, fields: { invite_code: "invite" } });
    expect(registerErrors(403).form).toBe("closed");
    expect(registerErrors(429).form).toBe("tooMany");
    expect(registerErrors(502).form).toBe("backendDown");
    expect(registerErrors(0).form).toBe("network");
    expect(registerErrors(500).form).toBe("failed");
    expect(registerErrors(422, "password must be at least 10 characters")).toEqual({
      form: null,
      fields: { password: "weakPassword" },
    });
    expect(registerErrors(422, [{ loc: ["body", "email"], msg: "bad", type: "x" }, { loc: ["body", "role"] }])).toEqual({
      form: "invalid",
      fields: { email: "invalidField" },
    });
  });

  it("maps sign-in and reset failures", () => {
    expect(loginError(401, null)).toEqual({ key: "wrong" });
    expect(loginError(429, "540")).toEqual({ key: "tooMany", minutes: 9 });
    expect(loginError(429, "nonsense")).toEqual({ key: "tooMany", minutes: 15 });
    expect(loginError(0, null).key).toBe("network");
    expect(resetError(400)).toBe("invalidLink");
    expect(resetError(422)).toBe("weakPassword");
    expect(resetError(500)).toBe("failed");
  });
});
