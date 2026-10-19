import { cleanup, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ActivitiesLoading from "@/app/(app)/activities/loading";
import ActivitiesPage from "@/app/(app)/activities/page";
import SyncPage from "@/app/(app)/sync/page";
import { ActivityDetailCard } from "@/features/activities/components/activity-detail";
import { settingsApi } from "@/features/settings/api";
import { ApiError, api } from "@/lib/api";
import { violations } from "./support/axe";
import { stubServerEnv } from "./support/env";
import { activity, page, syncStatus } from "./support/fixtures";
import { renderWithIntl } from "./support/intl";
import { me } from "./support/settings-fixtures";

const locale = vi.hoisted(() => ({ current: "en" as "en" | "tr" }));
vi.mock("next-intl/server", async () => {
  const { translatorFor } = await import("./support/intl");
  return { getTranslations: (namespace?: string) => translatorFor(locale.current)(namespace) };
});

async function renderActivities(params: Record<string, string> = {}) {
  renderWithIntl(await ActivitiesPage({ searchParams: Promise.resolve(params) }), locale.current);
}

beforeEach(() => {
  locale.current = "en";
  stubServerEnv();
  // The sport list falls back to common sports when the summary cannot be read.
  vi.spyOn(api, "summary").mockRejectedValue(new ApiError(502, "down"));
  vi.spyOn(api, "activities").mockResolvedValue(page([], null));
  vi.spyOn(settingsApi, "strava").mockResolvedValue({ connected: false });
});

describe("/activities for every kind of user", () => {
  it("without Strava: a way to connect it, no filters", async () => {
    await renderActivities();
    expect(screen.getByText("Strava is not connected")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Connect Strava" })).toHaveAttribute("href", "/me/connections");
    expect(screen.queryByRole("form", { name: "Filter activities" })).toBeNull();
  });

  it("connected but not synced yet: points to the sync page", async () => {
    vi.mocked(settingsApi.strava).mockResolvedValue({ connected: true });
    await renderActivities();
    expect(screen.getByText("No activities yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See sync status" })).toHaveAttribute("href", "/sync");
  });

  it("with filters: says the filters match nothing", async () => {
    vi.mocked(settingsApi.strava).mockResolvedValue({ connected: true });
    await renderActivities({ sport_type: "Swim" });
    expect(screen.getByText("No activities match these filters")).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Filter activities" })).toBeInTheDocument();
  });

  it("with activities, in Turkish, axe clean", async () => {
    locale.current = "tr";
    vi.mocked(api.activities).mockResolvedValue(page([1, 2], null));
    vi.mocked(settingsApi.strava).mockResolvedValue({ connected: true });
    await renderActivities();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Aktiviteler");
    cleanup();
    expect(await violations(await ActivitiesPage({ searchParams: Promise.resolve({}) }), "tr")).toEqual([]);
  });

  it("loading has a labelled skeleton", async () => {
    renderWithIntl(await ActivitiesLoading());
    expect(screen.getByRole("status", { name: "Loading activities" })).toBeInTheDocument();
  });

  it("the detail is axe clean in both languages", async () => {
    expect(await violations(<ActivityDetailCard activity={activity(1)} />, "tr")).toEqual([]);
    cleanup();
    renderWithIntl(<ActivityDetailCard activity={activity(1, { sport_type: "Ride" })} />, "tr");
    expect(screen.getByText("Ort. hız")).toBeInTheDocument();
  });
});

describe("/sync for a user without Strava", () => {
  it("makes Connect Strava the primary action and explains the empty runs", async () => {
    vi.spyOn(api, "syncStatus").mockResolvedValue(syncStatus({ athletes: [], rate_limit: null, last_synced_at: null }));
    vi.spyOn(api, "me").mockResolvedValue(me({ role: "user" }));
    renderWithIntl(await SyncPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByText("No Strava account connected")).toBeInTheDocument();
    expect(screen.getByText("Not synced yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Connect Strava" })).toHaveClass("bg-accent");
  });
});
