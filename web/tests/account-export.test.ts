// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET as exportData } from "@/app/api/account/export/route";
import { TEST_TOKEN, jsonResponse, sessionCookie, stubServerEnv } from "./support/env";

const fetchMock = vi.fn<typeof fetch>();
const ORIGIN = "http://localhost:3000";

const signedIn = () => new NextRequest(`${ORIGIN}/api/account/export`, { headers: { cookie: sessionCookie() } });

describe("export download (P8.14)", () => {
  beforeEach(() => {
    stubServerEnv();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-19T22:30:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("downloads GET /v1/me/export as the user, as a dated JSON attachment", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ user: { email: "runner@example.com" }, activities: [] }));
    const response = await exportData(signedIn());
    expect(response.status).toBe(200);
    expect(response.headers.get("content-disposition")).toBe('attachment; filename="trainsync-export-2026-10-19.json"');
    expect(response.headers.get("content-type")).toMatch(/^application\/json/);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(JSON.parse(await response.text())).toEqual({ user: { email: "runner@example.com" }, activities: [] });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe("http://api.test:8000/v1/me/export");
    expect(new Headers(init?.headers).get("authorization")).toBe(`Bearer ${TEST_TOKEN}`);
  });

  it("sends a signed-out browser to sign-in and passes other failures on without a file", async () => {
    const anonymous = await exportData(new NextRequest(`${ORIGIN}/api/account/export`));
    expect(anonymous.status).toBe(303);
    expect(anonymous.headers.get("location")).toBe("/login");
    expect(fetchMock).not.toHaveBeenCalled();
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "boom" }, 500));
    const failed = await exportData(signedIn());
    expect(failed.status).toBe(500);
    expect(failed.headers.get("content-disposition")).toBeNull();
  });
});
