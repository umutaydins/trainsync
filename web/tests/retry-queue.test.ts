import { describe, expect, it, vi } from "vitest";

import type { MutationResult } from "@/lib/mutate";
import { QUEUE_KEY, enqueue, flushQueue, isRetryable, readQueue } from "@/features/training/retry-queue";
import { memoryStore } from "./support/training-fixtures";

const ok: MutationResult<unknown> = { ok: true, status: 200, data: null };
const offline: MutationResult<unknown> = { ok: false, status: 0, error: "network error" };

describe("retry queue", () => {
  it("retries no answer, 5xx, 408 and 429, not other 4xx", () => {
    expect([0, 500, 502, 503, 408, 429].every(isRetryable)).toBe(true);
    expect([400, 401, 403, 404, 409, 422].some(isRetryable)).toBe(false);
  });

  it("keeps one entry per path, the newest body", () => {
    const store = memoryStore();
    enqueue(store, { path: "/v1/a", body: { reps: 5 }, queuedAt: 1 });
    enqueue(store, { path: "/v1/b", body: { reps: 6 }, queuedAt: 2 });
    enqueue(store, { path: "/v1/a", body: { reps: 7 }, queuedAt: 3 });
    expect(readQueue(store).map((e) => [e.path, e.body])).toEqual([
      ["/v1/b", { reps: 6 }],
      ["/v1/a", { reps: 7 }],
    ]);
  });

  it("flushes oldest first and empties the queue", async () => {
    const store = memoryStore();
    enqueue(store, { path: "/v1/a", body: 1, queuedAt: 1 });
    enqueue(store, { path: "/v1/b", body: 2, queuedAt: 2 });
    const send = vi.fn().mockResolvedValue(ok);
    const result = await flushQueue(store, send);
    expect(send.mock.calls).toEqual([
      ["/v1/a", 1],
      ["/v1/b", 2],
    ]);
    expect(result).toEqual({ sent: ["/v1/a", "/v1/b"], dropped: [], remaining: 0 });
    expect(store.data.has(QUEUE_KEY)).toBe(false);
  });

  it("stops at the first retryable failure and keeps the rest", async () => {
    const store = memoryStore();
    enqueue(store, { path: "/v1/a", body: 1, queuedAt: 1 });
    enqueue(store, { path: "/v1/b", body: 2, queuedAt: 2 });
    enqueue(store, { path: "/v1/c", body: 3, queuedAt: 3 });
    const send = vi.fn().mockResolvedValueOnce(ok).mockResolvedValueOnce(offline);
    const result = await flushQueue(store, send);
    expect(send).toHaveBeenCalledTimes(2);
    expect(result.sent).toEqual(["/v1/a"]);
    expect(result.remaining).toBe(2);
    expect(readQueue(store).map((e) => e.path)).toEqual(["/v1/b", "/v1/c"]);
  });

  it("drops entries the API rejects for good", async () => {
    const store = memoryStore();
    enqueue(store, { path: "/v1/a", body: 1, queuedAt: 1 });
    const send = vi.fn().mockResolvedValue({ ok: false, status: 409, error: "client_id belongs to another workout" });
    const result = await flushQueue(store, send);
    expect(result.dropped).toEqual([{ path: "/v1/a", status: 409, error: "client_id belongs to another workout" }]);
    expect(readQueue(store)).toEqual([]);
  });

  it("runs one flush at a time", async () => {
    const store = memoryStore();
    enqueue(store, { path: "/v1/a", body: 1, queuedAt: 1 });
    let release: (value: MutationResult<unknown>) => void = () => undefined;
    const send = vi.fn().mockImplementation(() => new Promise((resolve) => (release = resolve)));
    const first = flushQueue(store, send);
    const second = flushQueue(store, send);
    release(ok);
    expect(await first).toBe(await second);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("reads garbage as an empty queue", () => {
    const store = memoryStore();
    store.setItem(QUEUE_KEY, "nope");
    expect(readQueue(store)).toEqual([]);
    expect(readQueue(null)).toEqual([]);
  });
});
