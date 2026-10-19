import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SyncPage from "@/app/(app)/sync/page";
import { ApiError, api } from "@/lib/api";
import { stubServerEnv } from "./support/env";
import { renderWithIntl } from "./support/intl";
import { syncStatus } from "./support/fixtures";
import { me } from "./support/settings-fixtures";

vi.mock("next-intl/server", async () => {
  const { translatorFor } = await import("./support/intl");
  return { getTranslations: (namespace?: string) => translatorFor("en")(namespace) };
});

async function renderPage(params: Record<string, string> = {}) {
  renderWithIntl(await SyncPage({ searchParams: Promise.resolve(params) }));
}

describe("/sync page", () => {
  beforeEach(() => {
    stubServerEnv({ WEB_PUBLIC_URL: "https://dash.example" });
    vi.spyOn(api, "syncStatus").mockResolvedValue(syncStatus());
    vi.spyOn(api, "me").mockResolvedValue(me({ role: "user" }));
  });

  it("links Connect Strava to the BFF, which asks the API as the signed-in user", async () => {
    await renderPage();
    const href = screen.getByRole("link", { name: "Connect Strava" }).getAttribute("href");
    expect(href).toBe("/api/strava/connect");
  });

  it("confirms a fresh connection", async () => {
    await renderPage({ connected: "1" });
    expect(screen.getByText(/Strava connected/)).toBeInTheDocument();
  });

  it("shows a connect error from the callback", async () => {
    await renderPage({ connect_error: "strava authorization failed: access_denied" });
    expect(screen.getAllByRole("alert")[0]).toHaveTextContent("Connecting Strava failed");
    expect(screen.getAllByRole("alert")[0]).not.toHaveTextContent("access_denied");
  });

  it("shows an error state when the status cannot be loaded", async () => {
    vi.mocked(api.syncStatus).mockRejectedValue(new ApiError(502, "trainsync API unavailable"));
    await renderPage();
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load sync status");
    expect(screen.getByRole("alert")).not.toHaveTextContent("trainsync API unavailable");
  });
});
