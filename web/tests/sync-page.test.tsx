import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SyncPage from "@/app/(app)/sync/page";
import { ApiError, api } from "@/lib/api";
import { stubServerEnv } from "./support/env";
import { syncStatus } from "./support/fixtures";

async function renderPage(params: Record<string, string> = {}) {
  render(await SyncPage({ searchParams: Promise.resolve(params) }));
}

describe("/sync page", () => {
  beforeEach(() => {
    stubServerEnv({ TRAINSYNC_PUBLIC_API_URL: "https://api.example", WEB_PUBLIC_URL: "https://dash.example" });
    vi.spyOn(api, "syncStatus").mockResolvedValue(syncStatus());
  });

  it("links Connect Strava to the API login with this page as return_to", async () => {
    await renderPage();
    const href = screen.getByRole("link", { name: "Connect Strava" }).getAttribute("href") ?? "";
    const url = new URL(href);
    expect(`${url.origin}${url.pathname}`).toBe("https://api.example/auth/strava/login");
    expect(url.searchParams.get("return_to")).toBe("https://dash.example/sync");
    expect(href).not.toContain("test-api-key");
  });

  it("confirms a fresh connection", async () => {
    await renderPage({ connected: "1" });
    expect(screen.getByText(/Strava connected/)).toBeInTheDocument();
  });

  it("shows a connect error from the callback", async () => {
    await renderPage({ connect_error: "strava authorization failed: access_denied" });
    expect(screen.getAllByRole("alert")[0]).toHaveTextContent("access_denied");
  });

  it("shows an error state when the status cannot be loaded", async () => {
    vi.mocked(api.syncStatus).mockRejectedValue(new ApiError(502, "trainsync API unavailable"));
    await renderPage();
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load sync status");
  });
});
