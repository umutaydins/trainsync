import { beforeEach, describe, expect, it, vi } from "vitest";

import { CSRF_COOKIE, readCsrfCookie } from "@/lib/csrf-cookie";
import { del, mutate, post, put } from "@/lib/mutate";
import { jsonResponse } from "./support/env";

const TOKEN = "t".repeat(43);
const fetchMock = vi.fn<typeof fetch>();
const cookies = () => `theme=dark; ${CSRF_COOKIE}=${TOKEN}; other=1`;

function sent(): { url: string; init: RequestInit; headers: Headers } {
  const [url, init] = fetchMock.mock.calls[0] ?? [];
  return { url: String(url), init: init ?? {}, headers: new Headers(init?.headers) };
}

describe("readCsrfCookie", () => {
  it("finds the CSRF cookie among others", () => {
    expect(readCsrfCookie(cookies())).toBe(TOKEN);
    expect(readCsrfCookie(`${CSRF_COOKIE}=${TOKEN}`)).toBe(TOKEN);
  });

  it("returns null when it is missing or empty", () => {
    expect(readCsrfCookie("")).toBeNull();
    expect(readCsrfCookie("theme=dark")).toBeNull();
    expect(readCsrfCookie(`x${CSRF_COOKIE}=${TOKEN}`)).toBeNull();
    expect(readCsrfCookie(`${CSRF_COOKIE}=`)).toBeNull();
  });
});

describe("mutate", () => {
  beforeEach(() => {
    fetchMock.mockReset();
  });

  it("PUTs JSON through the BFF with the CSRF token", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 7, reps: 5 }));
    const result = await put<{ id: number; reps: number }>(
      "/v1/training/workouts/1/sets/abc",
      { reps: 5 },
      { fetchImpl: fetchMock, cookies },
    );
    expect(result).toEqual({ ok: true, status: 200, data: { id: 7, reps: 5 } });
    const { url, init, headers } = sent();
    expect(url).toBe("/api/ts/v1/training/workouts/1/sets/abc");
    expect(init.method).toBe("PUT");
    expect(init.body).toBe(JSON.stringify({ reps: 5 }));
    expect(init.credentials).toBe("same-origin");
    expect(headers.get("x-csrf-token")).toBe(TOKEN);
    expect(headers.get("content-type")).toBe("application/json");
  });

  it("reads document.cookie by default", async () => {
    document.cookie = `${CSRF_COOKIE}=${TOKEN}`;
    fetchMock.mockResolvedValue(jsonResponse({}, 201));
    await post("/v1/nutrition/foods", { name: "Oats" }, { fetchImpl: fetchMock });
    expect(sent().headers.get("x-csrf-token")).toBe(TOKEN);
    document.cookie = `${CSRF_COOKIE}=; max-age=0`;
  });

  it("sends a POST without a body as JSON", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, 200));
    await post("/v1/training/workouts/1/finish", undefined, { fetchImpl: fetchMock, cookies });
    const { init, headers } = sent();
    expect(init.body).toBeUndefined();
    expect(headers.get("content-type")).toBe("application/json");
  });

  it("DELETEs without a body or content type and handles 204", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const result = await del("/v1/training/workouts/1/sets/abc", { fetchImpl: fetchMock, cookies });
    expect(result).toEqual({ ok: true, status: 204, data: null });
    const { init, headers } = sent();
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
    expect(headers.get("content-type")).toBeNull();
    expect(headers.get("x-csrf-token")).toBe(TOKEN);
  });

  it("omits the header without a cookie (the BFF then answers 403)", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ error: "missing or invalid CSRF token" }, 403));
    const result = await mutate("POST", "/v1/training/workouts", {}, {
      fetchImpl: fetchMock,
      cookies: () => "",
    });
    expect(sent().headers.get("x-csrf-token")).toBeNull();
    expect(result).toEqual({ ok: false, status: 403, error: "missing or invalid CSRF token" });
  });

  it("returns errors with status and detail", async () => {
    const detail = [{ loc: ["body", "reps"], msg: "bad" }];
    fetchMock.mockResolvedValue(jsonResponse({ error: "invalid request parameters", detail }, 422));
    const result = await put("/v1/checkins/2026-10-18", { status: "x" }, { fetchImpl: fetchMock, cookies });
    expect(result).toEqual({ ok: false, status: 422, error: "invalid request parameters", detail });
  });

  it("falls back to a generic message for non-JSON errors", async () => {
    fetchMock.mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 }));
    const result = await post("/v1/training/workouts", {}, { fetchImpl: fetchMock, cookies });
    expect(result).toEqual({ ok: false, status: 502, error: "request failed (502)" });
  });

  it("reports network failures as status 0 instead of throwing", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const result = await post("/v1/training/workouts", {}, { fetchImpl: fetchMock, cookies });
    expect(result).toEqual({ ok: false, status: 0, error: "network error" });
  });

  it("only accepts API paths", async () => {
    await expect(post("/api/auth/logout", {}, { fetchImpl: fetchMock, cookies })).rejects.toThrow(
      /must start with \/v1\//,
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
