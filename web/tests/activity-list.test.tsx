import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ActivityList } from "@/features/activities/components/activity-list";
import { jsonResponse } from "./support/env";
import { page } from "./support/fixtures";

const QUERY = { limit: "50", sport_type: "Run" };

function rows(): string[] {
  const table = screen.getByTestId("activity-table");
  return within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) => row.getAttribute("data-activity-id") ?? "");
}

describe("ActivityList", () => {
  it("appends the next page without duplicates and stops at the end", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(page([3, 4, 5], "cursor-2")))
      .mockResolvedValueOnce(jsonResponse(page([5, 6], null)));
    vi.stubGlobal("fetch", fetchMock);
    render(<ActivityList initial={page([1, 2, 3], "cursor-1")} query={QUERY} />);
    expect(rows()).toEqual(["1", "2", "3"]);

    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Showing 5 activities")).toBeInTheDocument();
    expect(rows()).toEqual(["1", "2", "3", "4", "5"]);

    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("End of list")).toBeInTheDocument();
    expect(rows()).toEqual(["1", "2", "3", "4", "5", "6"]);
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();

    const urls = fetchMock.mock.calls.map(([url]) => new URL(String(url), "http://localhost"));
    expect(urls.map((u) => u.pathname)).toEqual(["/api/ts/v1/activities", "/api/ts/v1/activities"]);
    expect(urls.map((u) => u.searchParams.get("cursor"))).toEqual(["cursor-1", "cursor-2"]);
    expect(urls.every((u) => u.searchParams.get("sport_type") === "Run" && u.searchParams.get("limit") === "50")).toBe(true);
  });

  it("shows an error state and retries with the same cursor", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ error: "trainsync API unavailable" }, 502))
      .mockResolvedValueOnce(jsonResponse(page([2], null)));
    vi.stubGlobal("fetch", fetchMock);
    render(<ActivityList initial={page([1], "c1")} query={QUERY} />);

    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("trainsync API unavailable");
    expect(rows()).toEqual(["1"]);

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("End of list")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(rows()).toEqual(["1", "2"]);
    expect(fetchMock.mock.calls.map(([url]) => new URL(String(url), "http://x").searchParams.get("cursor"))).toEqual(["c1", "c1"]);
  });

  it("shows an empty state", () => {
    render(<ActivityList initial={page([], null)} query={QUERY} />);
    expect(screen.getByText("No activities match these filters")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("derives pace for runs and speed for rides", () => {
    const initial = page([1, 2], null);
    initial.items[1] = { ...initial.items[1]!, sport_type: "Ride", distance_m: 40_000, moving_time_s: 3600 };
    render(<ActivityList initial={initial} query={QUERY} />);
    expect(screen.getByText("5:00 /km")).toBeInTheDocument();
    expect(screen.getByText("40.0 km/h")).toBeInTheDocument();
  });
});
