// @vitest-environment node
import { NextRequest, type NextResponse } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DELETE, GET, PATCH, POST, PUT } from "@/app/api/ts/[...path]/route";
import { CSRF_COOKIE } from "@/lib/csrf-cookie";
import { BACKEND_UNREACHABLE, DEMO_READ_ONLY, MAX_BODY_BYTES, allowedMethods } from "@/lib/upstream";
import { TEST_TOKEN, jsonResponse, sessionCookie, stubServerEnv } from "./support/env";

const fetchMock = vi.fn<typeof fetch>();
const ORIGIN = "http://localhost:3000";
const TOKEN = "A".repeat(22) + "b".repeat(21);
const HANDLERS = { GET, POST, PUT, PATCH, DELETE } as const;
type HandlerMethod = keyof typeof HANDLERS;

interface Options {
  body?: BodyInit | null;
  headers?: Record<string, string>;
  cookieToken?: string | null;
  headerToken?: string | null;
  origin?: string | null;
}

function call(method: HandlerMethod, path: string, options: Options = {}): Promise<NextResponse> {
  const headers: Record<string, string> = {};
  const origin = options.origin === undefined ? ORIGIN : options.origin;
  if (origin !== null) headers.origin = origin;
  const cookieToken = options.cookieToken === undefined ? TOKEN : options.cookieToken;
  const cookies = [sessionCookie()];
  if (cookieToken !== null) cookies.push(`${CSRF_COOKIE}=${cookieToken}`);
  headers.cookie = cookies.join("; ");
  const headerToken = options.headerToken === undefined ? TOKEN : options.headerToken;
  if (headerToken !== null) headers["x-csrf-token"] = headerToken;
  if (options.body !== undefined && options.body !== null) headers["content-type"] = "application/json";
  Object.assign(headers, options.headers);
  const request = new NextRequest(`${ORIGIN}/api/ts/${path}`, {
    method,
    headers,
    body: options.body ?? null,
    // Required by Node for streaming request bodies.
    ...(options.body instanceof ReadableStream ? { duplex: "half" } : {}),
  });
  // Next.js hands the handler decoded segments; mimic that.
  const segments = path.split("?")[0]?.split("/").map(decodeURIComponent) ?? [];
  return HANDLERS[method](request, { params: Promise.resolve({ path: segments }) });
}

const SET = "v1/training/workouts/42/sets/0b9c7a52-5d0e-4c43-9a8e-2f1d6c7b8a90";
const SET_BODY = JSON.stringify({ exercise_id: 3, reps: 5, weight_kg: 100 });

describe("BFF allowlist (method × path)", () => {
  beforeEach(() => {
    stubServerEnv();
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
  });

  // [method, path, expected status]: 200 forwarded, 404 unknown path, 405 known path, wrong method.
  const TABLE: [HandlerMethod, string, number][] = [
    ["GET", "v1/activities", 200],
    ["GET", "v1/activities/123", 200],
    ["GET", "v1/stats/weekly", 200],
    ["GET", "v1/stats/summary", 200],
    ["GET", "v1/sync/status", 200],
    ["GET", "v1/training", 200],
    ["GET", "v1/training/programs/7", 200],
    ["GET", "v1/nutrition/log/2026-10-18", 200],
    ["GET", "v1/checkins/2026-10-18", 200],
    ["POST", "v1/training/workouts", 200],
    ["PUT", SET, 200],
    ["DELETE", SET, 200],
    ["POST", "v1/nutrition/foods", 200],
    ["PUT", "v1/nutrition/log/2026-10-18/abc-123", 200],
    ["DELETE", "v1/nutrition/log/abc-123", 200],
    ["PUT", "v1/checkins/2026-10-18", 200],
    ["PATCH", "v1/training/workouts/42", 405],
    ["PATCH", "v1/nutrition/foods/1", 200],
    ["PATCH", "v1/nutrition/log/abc-123", 405],
    ["PATCH", "v1/training/exercises/12", 200],
    ["POST", "v1/activities", 405],
    ["PUT", "v1/activities/123", 405],
    ["DELETE", "v1/activities/123", 405],
    ["POST", "v1/sync/status", 405],
    ["DELETE", "v1/stats/summary", 405],
    ["GET", "v1/trainingx", 404],
    ["POST", "v1/trainingx/workouts", 404],
    ["POST", "v1/sync/backfill", 404],
    ["POST", "auth/strava/login", 404],
    ["POST", "webhooks/strava", 404],
    ["DELETE", "metrics", 404],
    ["GET", "health/ready", 404],
    ["POST", "v1", 404],
    ["PUT", "v2/training/workouts", 404],
  ];

  it.each(TABLE)("%s %s → %i", async (method, path, status) => {
    const body = method === "POST" || method === "PUT" || method === "PATCH" ? SET_BODY : undefined;
    const response = await call(method, path, { body });
    expect(response.status).toBe(status);
    expect(fetchMock).toHaveBeenCalledTimes(status === 200 ? 1 : 0);
    if (status === 405) expect(response.headers.get("allow")).toMatch(/^GET/);
  });

  it("lists the allowed methods in Allow", async () => {
    const response = await call("PATCH", "v1/training/workouts/42", { body: "{}" });
    expect(response.headers.get("allow")).toBe("GET, POST, PUT, DELETE");
  });

  // Each of these, once decoded and joined, would leave /v1/training if it reached the URL parser.
  it.each([
    "v1/training/../../metrics",
    "v1/training/..",
    "v1/training/.",
    "v1/training/%2e%2e/%2e%2e/metrics",
    "v1/training/a%2F..%2F..%2F..%2Fmetrics",
    "v1/training/a%5C..%5Cmetrics",
    "v1/training/%252e%252e/metrics",
    "v1/training/.hidden",
    "v1/training//workouts",
    "v1/training/a%00b",
    "v1/training/a%20b",
    "v1/training/a%3Fx%3D1",
    "v1/training/a%23frag",
    "v1/training/a@evil.example",
  ])("rejects traversal or odd segments in %s", async (path) => {
    for (const method of ["GET", "POST", "PUT", "DELETE"] as const) {
      const body = method === "POST" || method === "PUT" ? "{}" : undefined;
      expect((await call(method, path, { body })).status).toBe(404);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("matches only validated paths", () => {
    expect(allowedMethods("/v1/training/workouts/42")).toEqual(["GET", "POST", "PUT", "DELETE"]);
    expect(allowedMethods("/v1/training/a/../../../metrics")).toBeNull();
    expect(allowedMethods("v1/training")).toBeNull();
    expect(allowedMethods(`/v1/training${"/x".repeat(20)}`)).toBeNull();
  });
});

describe("BFF mutations: CSRF", () => {
  beforeEach(() => {
    stubServerEnv();
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(jsonResponse({ client_id: "x" }, 201));
    vi.stubGlobal("fetch", fetchMock);
  });

  it("forwards a correct mutation with the API key, body and query", async () => {
    const response = await call("PUT", `${SET}?dry_run=1`, { body: SET_BODY });
    expect(response.status).toBe(201);
    expect(await response.json()).toEqual({ client_id: "x" });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe(`http://api.test:8000/${SET}?dry_run=1`);
    expect(init?.method).toBe("PUT");
    expect(init?.body).toBe(SET_BODY);
    const headers = new Headers(init?.headers);
    expect(headers.get("authorization")).toBe(`Bearer ${TEST_TOKEN}`);
    expect(headers.get("content-type")).toBe("application/json");
    // Browser credentials never travel upstream.
    expect(headers.get("cookie")).toBeNull();
    expect(headers.get("x-csrf-token")).toBeNull();
  });

  it("accepts a same-origin Referer when Origin is absent", async () => {
    const response = await call("POST", "v1/training/workouts", {
      body: "{}",
      origin: null,
      headers: { referer: `${ORIGIN}/training/today?x=1` },
    });
    expect(response.status).toBe(201);
  });

  it("uses WEB_PUBLIC_URL as the allowed origin", async () => {
    stubServerEnv({ WEB_PUBLIC_URL: "https://dash.example.com/" });
    const ok = await call("POST", "v1/training/workouts", {
      body: "{}",
      origin: "https://dash.example.com",
    });
    expect(ok.status).toBe(201);
    const local = await call("POST", "v1/training/workouts", { body: "{}", origin: ORIGIN });
    expect(local.status).toBe(403);
  });

  it.each<[string, Options]>([
    ["no Origin and no Referer", { origin: null }],
    ["a foreign Origin", { origin: "https://evil.example" }],
    ["a look-alike Origin", { origin: "http://localhost:3000.evil.example" }],
    ["another port", { origin: "http://localhost:3001" }],
    ["another scheme", { origin: "https://localhost:3000" }],
    ["Origin: null", { origin: "null" }],
    ["a foreign Referer", { origin: null, headers: { referer: "https://evil.example/localhost:3000" } }],
    ["a foreign Origin with a same-origin Referer", {
      origin: "https://evil.example",
      headers: { referer: `${ORIGIN}/` },
    }],
  ])("403 for %s", async (_name, options) => {
    const response = await call("POST", "v1/training/workouts", { body: "{}", ...options });
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ error: "cross-origin request refused" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each<[string, Options]>([
    ["no token header", { headerToken: null }],
    ["no token cookie", { cookieToken: null }],
    ["neither", { headerToken: null, cookieToken: null }],
    ["a different token", { headerToken: "B".repeat(43) }],
    ["a malformed token in both", { headerToken: "short", cookieToken: "short" }],
    ["an empty token in both", { headerToken: "", cookieToken: "" }],
  ])("403 for %s", async (_name, options) => {
    for (const method of ["POST", "PUT", "DELETE"] as const) {
      const response = await call(method, SET, { body: "{}", ...options });
      expect(response.status).toBe(403);
      expect(await response.json()).toEqual({ error: "missing or invalid CSRF token" });
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not require a CSRF token for reads", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [] }));
    const response = await call("GET", "v1/training/workouts", {
      origin: null,
      cookieToken: null,
      headerToken: null,
    });
    expect(response.status).toBe(200);
  });
});

describe("BFF mutations: body rules", () => {
  beforeEach(() => {
    stubServerEnv();
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(jsonResponse({}, 200));
    vi.stubGlobal("fetch", fetchMock);
  });

  it.each(["text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", "application/jsonx"])(
    "415 for POST with %s",
    async (type) => {
      const response = await call("POST", "v1/training/workouts", {
        body: "{}",
        headers: { "content-type": type },
      });
      expect(response.status).toBe(415);
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it("415 for PUT without a content type", async () => {
    const response = await call("PUT", SET);
    expect(response.status).toBe(415);
  });

  it("accepts application/json with a charset", async () => {
    const response = await call("POST", "v1/training/workouts", {
      body: "{}",
      headers: { "content-type": "application/json; charset=utf-8" },
    });
    expect(response.status).toBe(200);
  });

  it("forwards a DELETE without a body", async () => {
    const response = await call("DELETE", SET);
    expect(response.status).toBe(200);
    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(init?.body).toBeNull();
    expect(new Headers(init?.headers).get("content-type")).toBeNull();
  });

  it("415 for a DELETE with a non-JSON body", async () => {
    const response = await call("DELETE", SET, {
      body: "x=1",
      headers: { "content-type": "text/plain" },
    });
    expect(response.status).toBe(415);
  });

  it("400 for a body that is not JSON", async () => {
    const response = await call("POST", "v1/training/workouts", { body: "{not json" });
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "invalid JSON body" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards a body of exactly the limit", async () => {
    const body = JSON.stringify({ note: "x".repeat(MAX_BODY_BYTES - 11) });
    expect(Buffer.byteLength(body)).toBe(MAX_BODY_BYTES);
    expect((await call("POST", "v1/nutrition/foods", { body })).status).toBe(200);
  });

  it("413 for a body over the limit", async () => {
    const body = JSON.stringify({ note: "x".repeat(MAX_BODY_BYTES) });
    const response = await call("POST", "v1/nutrition/foods", { body });
    expect(response.status).toBe(413);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("413 from a lying Content-Length: the stream is read with a cap", async () => {
    let pulled = 0;
    const chunk = new Uint8Array(16 * 1024).fill(0x20);
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        pulled += 1;
        controller.enqueue(chunk);
      },
    });
    const response = await call("POST", "v1/nutrition/foods", {
      body: stream,
      headers: { "content-length": "2" },
    });
    expect(response.status).toBe(413);
    // An endless body: reading stopped right after the limit.
    expect(pulled).toBeLessThanOrEqual(MAX_BODY_BYTES / chunk.byteLength + 2);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("413 from a declared Content-Length over the limit without reading", async () => {
    const response = await call("POST", "v1/nutrition/foods", {
      body: "{}",
      headers: { "content-length": String(MAX_BODY_BYTES + 1) },
    });
    expect(response.status).toBe(413);
  });
});

describe("BFF mutations: upstream answers", () => {
  beforeEach(() => {
    stubServerEnv();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("passes 409 and 422 through with their status and detail", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "workout already finished" }, 409));
    const conflict = await call("PUT", SET, { body: SET_BODY });
    expect(conflict.status).toBe(409);
    expect(await conflict.json()).toEqual({
      error: "workout already finished",
      detail: "workout already finished",
    });

    const detail = [{ loc: ["body", "reps"], msg: "must be > 0", type: "value_error" }];
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail }, 422));
    const invalid = await call("PUT", SET, { body: SET_BODY });
    expect(invalid.status).toBe(422);
    expect(await invalid.json()).toEqual({ error: "invalid request parameters", detail });
  });

  it("keeps upstream auth failures opaque and ends a session the API refused", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: `bad token ${TEST_TOKEN}` }, 401));
    const response = await call("POST", "v1/training/workouts", { body: "{}" });
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ error: "not signed in" });
    expect(response.headers.get("set-cookie")).toMatch(/ts_session=;/);
  });

  it("says so when the read-only demo refuses a write, and only for its marked 403", async () => {
    const demo = new Response(JSON.stringify({ detail: "This is a read-only demo." }), {
      status: 403,
      headers: { "content-type": "application/json", "x-trainsync-demo": "read-only" },
    });
    fetchMock.mockResolvedValueOnce(demo);
    const refused = await call("PUT", SET, { body: SET_BODY });
    expect(refused.status).toBe(403);
    expect(await refused.json()).toEqual({ error: DEMO_READ_ONLY });
    expect(refused.headers.get("x-trainsync-demo")).toBeNull();

    // A 403 without the marker stays an opaque authorization failure.
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "This is a read-only demo." }, 403));
    const plain = await call("PUT", SET, { body: SET_BODY });
    expect(await plain.json()).toEqual({ error: "not allowed" });
  });

  it("answers 204 without a body", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const response = await call("DELETE", SET);
    expect(response.status).toBe(204);
    expect(await response.text()).toBe("");
  });

  it("returns 502 when the API is unreachable", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError(`fetch failed ${TEST_TOKEN}`));
    const response = await call("POST", "v1/training/workouts", { body: "{}" });
    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ error: BACKEND_UNREACHABLE });
  });

  it("never echoes the API key or upstream headers", async () => {
    const leaky = () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 201,
        headers: {
          "content-type": "application/json",
          "x-api-key": TEST_TOKEN,
          "set-cookie": `upstream=${TEST_TOKEN}`,
          "x-upstream-debug": TEST_TOKEN,
        },
      });
    fetchMock.mockImplementation(async () => leaky());
    const responses = [
      await call("POST", "v1/training/workouts", { body: "{}" }),
      await call("PUT", SET, { body: SET_BODY }),
      await call("DELETE", SET),
      await call("POST", "v1/training/workouts", { body: "{}", headerToken: null }),
      await call("POST", "v1/training/workouts", { body: "{nope" }),
    ];
    for (const response of responses) {
      const headers = [...response.headers.entries()].map(([k, v]) => `${k}: ${v}`).join("\n");
      expect(`${headers}\n${await response.text()}`).not.toContain(TEST_TOKEN);
      expect(response.headers.get("x-upstream-debug")).toBeNull();
      expect(response.headers.get("set-cookie")).toBeNull();
    }
  });
});
