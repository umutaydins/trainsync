import { act, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { REFRESH_MS, SyncStatusView } from "@/features/sync/components/sync-status-view";
import { jsonResponse } from "./support/env";
import { renderWithIntl as render } from "./support/intl";
import { syncStatus } from "./support/fixtures";

describe("SyncStatusView", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("shows runs, webhook counts, rate-limit bars and breaker badges", () => {
    render(<SyncStatusView initial={syncStatus()} />);
    const backfill = screen.getByTestId("run-backfill");
    expect(backfill).toHaveAttribute("data-status", "succeeded");
    expect(within(backfill).getByText("Succeeded")).toHaveClass("text-ok");
    expect(within(screen.getByTestId("run-incremental")).getByText("never ran")).toBeInTheDocument();
    expect(screen.getByText("Dead letters").nextElementSibling).toHaveTextContent("1");
    expect(screen.getByRole("progressbar", { name: "15 minutes" })).toHaveAttribute("aria-valuenow", "85");
    expect(screen.getByRole("progressbar", { name: "Daily" })).toHaveAttribute("aria-valuenow", "10");
    expect(screen.getByText("worker-1").nextElementSibling).toHaveTextContent("Half-open");
    expect(screen.getByText("api").nextElementSibling).toHaveClass("text-ok");
  });

  it("refreshes every 15 s through the BFF", async () => {
    const next = syncStatus({ circuit: { state: "open", processes: [] } });
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(next));
    vi.stubGlobal("fetch", fetchMock);
    render(<SyncStatusView initial={syncStatus()} />);
    expect(REFRESH_MS).toBe(15_000);

    await act(() => vi.advanceTimersByTimeAsync(REFRESH_MS - 1));
    expect(fetchMock).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(fetchMock).toHaveBeenCalledWith("/api/ts/v1/sync/status", { cache: "no-store" });
    expect(screen.getByText("Open")).toHaveClass("text-bad");
    expect(screen.getByText("No process has reported yet.")).toBeInTheDocument();
  });

  it("keeps the last data and shows an error when a refresh fails", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ error: "trainsync API unavailable" }, 502)));
    render(<SyncStatusView initial={syncStatus()} />);
    await act(() => vi.advanceTimersByTimeAsync(REFRESH_MS));
    expect(screen.getByRole("alert")).toHaveTextContent("Refresh failed, showing the last known state");
    expect(screen.getByRole("alert")).not.toHaveTextContent("trainsync API unavailable");
    expect(screen.getByTestId("run-backfill")).toHaveAttribute("data-status", "succeeded");
  });

  it("shows empty states before anything is connected", () => {
    render(<SyncStatusView initial={syncStatus({ athletes: [], rate_limit: null })} />);
    expect(screen.getByText("No Strava account connected")).toBeInTheDocument();
    expect(screen.getByText("No usage yet")).toBeInTheDocument();
  });

  it("speaks Turkish", () => {
    render(<SyncStatusView initial={syncStatus()} />, "tr");
    expect(within(screen.getByTestId("run-backfill")).getByText("Başarılı")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "15 dakika" })).toBeInTheDocument();
  });
});
