import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/features/auth/components/login-form";

describe("LoginForm", () => {
  it("shows an error on 401", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response("{}", { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<LoginForm next="/sync" />);

    await userEvent.type(screen.getByLabelText("Password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong password.");
    const body = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(body.get("password")).toBe("nope");
    expect(body.get("next")).toBe("/sync");
  });

  it("says when to try again on 429", async () => {
    const response = new Response("{}", { status: 429, headers: { "retry-after": "540" } });
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(response));
    render(<LoginForm next="/" />);

    await userEvent.type(screen.getByLabelText("Password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Too many failed attempts. Try again in 9 min.");
  });
});
