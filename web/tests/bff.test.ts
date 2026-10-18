// @vitest-environment node
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DELETE, GET, PATCH, POST, PUT } from "@/app/api/ts/[...path]/route";
import { BACKEND_UNREACHABLE } from "@/lib/upstream";
import { TEST_API_KEY, jsonResponse, stubServerEnv } from "./support/env";

const fetchMock = vi.fn<typeof fetch>();

function call(path: string, query = "") {
  const request = new NextRequest(`http://localhost:3000/api/ts/${path}${query}`);
  return GET(request, { params: Promise.resolve({ path: path.split("/") }) });
}

async function text(response: Response): Promise<string> {
  const headers = [...response.headers.entries()].map(([k, v]) => `${k}: ${v}`).join("\n");
  return `${headers}\n${await response.clone().text()}`;
}

describe("BFF /api/ts/[...path]", () => {
  beforeEach(() => {
    stubServerEnv();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("forwards allowlisted GETs with the API key and the query string", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], next_cursor: null, last_synced_at: null }));
    const response = await call("v1/activities", "?sport_type=Run&limit=5&cursor=abc");

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ items: [], next_cursor: null, last_synced_at: null });
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe(
      "http://api.test:8000/v1/activities?sport_type=Run&limit=5&cursor=abc",
    );
    expect(init?.method).toBe("GET");
    expect(new Headers(init?.headers).get("x-api-key")).toBe(TEST_API_KEY);
  });

  it.each([
    "v1/activities/10000000123",
    "v1/stats/weekly",
    "v1/stats/summary",
    "v1/sync/status",
  ])("allows %s", async (path) => {
    fetchMock.mockResolvedValue(jsonResponse({}));
    expect((await call(path)).status).toBe(200);
  });

  it.each([
    "health/ready",
    "metrics",
    "auth/strava/login",
    "webhooks/strava",
    "v1/activities/abc",
    "v1/activities/1/../../metrics",
    "v1/activities/..",
    "v2/activities",
    "v1/stats",
  ])("rejects %s without calling the API", async (path) => {
    const response = await call(path);
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "not found" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ["POST", POST],
    ["PUT", PUT],
    ["PATCH", PATCH],
    ["DELETE", DELETE],
  ])("rejects %s on read-only paths with 405", async (method, handler) => {
    const path = "v1/sync/status";
    const request = new NextRequest(`http://localhost:3000/api/ts/${path}`, { method });
    const response = await handler(request, { params: Promise.resolve({ path: path.split("/") }) });
    expect(response.status).toBe(405);
    expect(response.headers.get("allow")).toBe("GET");
    expect(await response.json()).toEqual({ error: "method not allowed" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("maps upstream errors to {error} with the same status", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "activity not found" }, 404));
    const response = await call("v1/activities/42");
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ error: "activity not found" });
  });

  it("maps validation errors and 401s without leaking details", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: [{ msg: "bad" }] }, 422));
    expect(await (await call("v1/activities", "?limit=900")).json()).toEqual({
      error: "invalid request parameters",
    });
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "invalid or missing API key" }, 401));
    const unauthorized = await call("v1/sync/status");
    expect(unauthorized.status).toBe(401);
    expect(await unauthorized.json()).toEqual({
      error: "the web app is not authorized for the trainsync API",
    });
  });

  it("returns 502 when the API is unreachable", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const response = await call("v1/stats/weekly");
    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ error: BACKEND_UNREACHABLE });
  });

  it("never echoes the API key in responses", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [] }));
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "boom" }, 500));
    fetchMock.mockRejectedValueOnce(new Error(`connect failed with ${TEST_API_KEY}`));
    const responses = [
      await call("v1/activities"),
      await call("v1/activities"),
      await call("v1/activities"),
      await call("metrics"),
      await POST(new NextRequest("http://localhost:3000/api/ts/v1/sync/status", { method: "POST" }), {
        params: Promise.resolve({ path: ["v1", "sync", "status"] }),
      }),
    ];
    for (const response of responses) {
      expect(await text(response)).not.toContain(TEST_API_KEY);
    }
  });
});
