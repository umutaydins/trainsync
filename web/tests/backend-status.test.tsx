import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ErrorPage from "@/app/(app)/error";
import { backendReachable } from "@/features/shell/backend-status";
import { BACKEND_UNREACHABLE_TITLE } from "@/lib/backend-copy";
import { BACKEND_UNREACHABLE, upstreamGet } from "@/lib/upstream";
import { jsonResponse, stubServerEnv } from "./support/env";

beforeEach(() => stubServerEnv());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("backend reachability (P7.6)", () => {
  it("probes the API's liveness without a key", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ status: "ok" }));
    expect(await backendReachable(fetchMock)).toBe(true);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("http://api.test:8000/health/live");
    expect(JSON.stringify(init)).not.toContain("X-API-Key");
  });

  it("is false on a network error, a timeout or an error status", async () => {
    expect(await backendReachable(vi.fn<typeof fetch>().mockRejectedValue(new TypeError("fetch failed")))).toBe(false);
    expect(await backendReachable(vi.fn<typeof fetch>().mockRejectedValue(new DOMException("timeout", "TimeoutError")))).toBe(false);
    expect(await backendReachable(vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({}, 503)))).toBe(false);
  });

  it("a data call to an offline backend gets the friendly message", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("fetch failed")));
    const result = await upstreamGet("/v1/sync/status", new URLSearchParams());
    expect(result).toEqual({ ok: false, status: 502, error: BACKEND_UNREACHABLE });
  });

  it("the error page says the backend is unreachable when it is", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ reachable: false })));
    render(<ErrorPage error={new Error("x")} reset={() => undefined} />);
    expect(await screen.findByText(BACKEND_UNREACHABLE_TITLE)).toBeInTheDocument();
    expect(screen.getByText(/asleep or offline/)).toBeInTheDocument();
  });

  it("and a generic error when the backend answers", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ reachable: true })));
    render(<ErrorPage error={new Error("x")} reset={() => undefined} />);
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/backend-status", expect.anything()));
    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(screen.queryByText(BACKEND_UNREACHABLE_TITLE)).not.toBeInTheDocument();
  });
});
