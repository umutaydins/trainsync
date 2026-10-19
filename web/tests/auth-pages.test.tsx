import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ForgotPasswordPage from "@/app/forgot-password/page";
import LoginPage from "@/app/login/page";
import PrivacyPage from "@/app/privacy/page";
import ResetPasswordPage from "@/app/reset-password/page";
import TermsPage from "@/app/terms/page";
import { ResetForm } from "@/features/auth/components/reset-form";
import { SignOutButton } from "@/features/auth/components/sign-out-button";
import type { Locale } from "@/i18n/config";
import { OWNER_CONTACT_PLACEHOLDER } from "@/lib/env";
import { renderWithIntl } from "./support/intl";

const locale = vi.hoisted(() => ({ current: "en" as "en" | "tr" }));
const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next-intl/server", async () => {
  const { translatorFor: forLocale } = await import("./support/intl");
  return { getTranslations: (namespace?: string) => forLocale(locale.current)(namespace) };
});
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/" }));

const NO_PARAMS = Promise.resolve({});

/** axe over a whole page (the auth layout brings its own landmarks). */
async function pageViolations(ui: ReactElement, lang: Locale = "en"): Promise<string[]> {
  const { container } = renderWithIntl(ui, lang);
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  return result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

describe("signed-out pages (P8.13)", () => {
  beforeEach(() => {
    locale.current = "en";
  });

  it("sign-in shows the reset notice and links the legal pages", async () => {
    renderWithIntl(await LoginPage({ searchParams: Promise.resolve({ reset: "1" }) }));
    expect(screen.getByRole("heading", { level: 1, name: "Back at it." })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Password changed.");
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy");
    expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
  });

  it("forgot password explains the owner's reset link", async () => {
    renderWithIntl(await ForgotPasswordPage());
    expect(screen.getByText(/Ask the owner for a reset link/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to sign in" })).toHaveAttribute("href", "/login");
  });

  it("a reset page without a token says what is missing", async () => {
    renderWithIntl(await ResetPasswordPage({ searchParams: NO_PARAMS }));
    expect(screen.getByRole("alert")).toHaveTextContent("needs the reset link");
  });

  it.each<[string, () => Promise<ReactElement>]>([
    ["login", () => LoginPage({ searchParams: NO_PARAMS })],
    ["forgot password", () => ForgotPasswordPage()],
    ["reset password", () => ResetPasswordPage({ searchParams: Promise.resolve({ token: "t0k" }) })],
    ["privacy", () => PrivacyPage()],
    ["terms", () => TermsPage()],
  ])("%s has no axe violations", async (_name, page) => {
    expect(await pageViolations(await page())).toEqual([]);
  });
});

describe("reset form", () => {
  it("checks the confirmation, posts the token and goes to sign-in", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    renderWithIntl(<ResetForm token="t0k" />);
    await userEvent.type(screen.getByLabelText("New password"), "a brand new password");
    await userEvent.type(screen.getByLabelText("Repeat the new password"), "a different password");
    await userEvent.click(screen.getByRole("button", { name: "Save the new password" }));
    expect(screen.getByText("The passwords do not match.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    await userEvent.clear(screen.getByLabelText("Repeat the new password"));
    await userEvent.type(screen.getByLabelText("Repeat the new password"), "a brand new password");
    await userEvent.click(screen.getByRole("button", { name: "Save the new password" }));
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ token: "t0k", password: "a brand new password" });
    expect(router.push).toHaveBeenCalledWith("/login?reset=1");
  });

  it("says when the link is used up", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(new Response("{}", { status: 400 })));
    renderWithIntl(<ResetForm token="old" />, "tr");
    await userEvent.type(screen.getByLabelText("Yeni şifre"), "a brand new password");
    await userEvent.type(screen.getByLabelText("Yeni şifreyi tekrar yaz"), "a brand new password");
    await userEvent.click(screen.getByRole("button", { name: "Yeni şifreyi kaydet" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bu sıfırlama bağlantısı geçersiz");
  });
});

describe("sign out", () => {
  it("posts to the logout route", () => {
    const { container } = renderWithIntl(<SignOutButton />, "tr");
    expect(container.querySelector("form")).toHaveAttribute("action", "/api/auth/logout");
    expect(screen.getByRole("button", { name: /Çıkış|Oturumu kapat/ })).toHaveAttribute("type", "submit");
  });
});

describe("legal pages", () => {
  it.each<["en" | "tr", string, string]>([
    ["en", "Your Strava data", "Not medical advice"],
    ["tr", "Strava verilerin", "Tıbbi tavsiye değildir"],
  ])("render in %s with the contact address", async (lang, privacyHeading, termsHeading) => {
    locale.current = lang;
    vi.stubEnv("OWNER_CONTACT_EMAIL", "");
    const privacy = renderWithIntl(await PrivacyPage(), lang);
    expect(screen.getByRole("heading", { level: 2, name: new RegExp(privacyHeading) })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: OWNER_CONTACT_PLACEHOLDER })).toHaveAttribute(
      "href",
      `mailto:${OWNER_CONTACT_PLACEHOLDER}`,
    );
    privacy.unmount();
    vi.stubEnv("OWNER_CONTACT_EMAIL", "me@trainsync.example");
    renderWithIntl(await TermsPage(), lang);
    expect(screen.getByRole("heading", { level: 2, name: new RegExp(termsHeading) })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "me@trainsync.example" })).toBeInTheDocument();
  });

  it.each<[string, () => Promise<ReactElement>]>([
    ["privacy", () => PrivacyPage()],
    ["terms", () => TermsPage()],
  ])("Turkish %s has no axe violations", async (_name, page) => {
    locale.current = "tr";
    expect(await pageViolations(await page(), "tr")).toEqual([]);
  });
});

