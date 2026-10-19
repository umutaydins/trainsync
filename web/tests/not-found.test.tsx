import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import NotFound from "@/app/(app)/not-found";
import { renderWithIntl } from "./support/intl";

const locale = vi.hoisted(() => ({ current: "en" as "en" | "tr" }));

vi.mock("next-intl/server", async () => {
  const { translatorFor } = await import("./support/intl");
  return { getTranslations: (namespace?: string) => translatorFor(locale.current)(namespace) };
});

async function renderNotFound(lang: "en" | "tr") {
  locale.current = lang;
  renderWithIntl(await NotFound(), lang);
}

describe("not-found page", () => {
  it("has the page's one h1 and a way back, in English", async () => {
    await renderNotFound("en");
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Today" })).toHaveAttribute("href", "/");
  });

  it("and in Turkish", async () => {
    await renderNotFound("tr");
    expect(screen.getByRole("heading", { level: 1, name: "Sayfa bulunamadı" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Bugün'e dön" })).toHaveAttribute("href", "/");
  });
});
