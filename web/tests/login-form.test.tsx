import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/features/auth/components/login-form";
import { renderWithIntl } from "./support/intl";

describe("LoginForm", () => {
  it("shows an error on 401", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response("{}", { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    renderWithIntl(<LoginForm next="/sync" />);

    await userEvent.type(screen.getByLabelText("Email"), "runner@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong email or password.");
    const body = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(body.get("email")).toBe("runner@example.com");
    expect(body.get("password")).toBe("nope");
    expect(body.get("next")).toBe("/sync");
  });

  it("says when to try again on 429", async () => {
    const response = new Response("{}", { status: 429, headers: { "retry-after": "540" } });
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(response));
    renderWithIntl(<LoginForm next="/" />);

    await userEvent.type(screen.getByLabelText("Email"), "runner@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many failed attempts. Try again in 9 min.");
  });

  it("speaks Turkish and links to sign-up and the forgotten-password page", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(new Response("{}", { status: 401 })));
    renderWithIntl(<LoginForm next="/" />, "tr");
    expect(screen.getByRole("link", { name: "Hesap oluştur" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: "Şifreni mi unuttun?" })).toHaveAttribute("href", "/forgot-password");
    await userEvent.type(screen.getByLabelText("E-posta"), "runner@example.com");
    await userEvent.type(screen.getByLabelText("Şifre"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Giriş yap" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("E-posta ya da şifre yanlış.");
  });

  it("reports a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("offline")));
    renderWithIntl(<LoginForm next="/" />);
    await userEvent.type(screen.getByLabelText("Email"), "runner@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Network error. Try again.");
  });
});
