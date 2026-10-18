/**
 * A small localStorage queue of idempotent PUTs that did not get an answer (status 0) or got a
 * 5xx. Replaying is always safe: each entry is keyed by its path, which carries the client id
 * (ADR 0017). Flushed on the browser's `online` event and after the next successful write.
 * This is a retry queue, not offline-first logging: the page itself still needs the network.
 */

import type { KeyValueStore } from "@/lib/timers";
import type { MutationResult } from "@/lib/mutate";

export const QUEUE_KEY = "trainsync.pending-puts";
export const MAX_ENTRIES = 200;

export interface PendingPut {
  /** API path, e.g. `/v1/training/workouts/42/sets/<uuid>`; the dedupe key. */
  path: string;
  body: unknown;
  queuedAt: number;
}

export type Send = (path: string, body: unknown) => Promise<MutationResult<unknown>>;

export interface FlushResult {
  sent: string[];
  /** Rejected with a 4xx: retrying cannot help, so they leave the queue. */
  dropped: { path: string; status: number; error: string }[];
  remaining: number;
}

/** 0 (no answer) and 5xx are worth retrying; a 4xx answer is final. */
export function isRetryable(status: number): boolean {
  return status === 0 || status >= 500 || status === 429 || status === 408;
}

export function readQueue(store: KeyValueStore | null): PendingPut[] {
  if (!store) return [];
  try {
    const value: unknown = JSON.parse(store.getItem(QUEUE_KEY) ?? "[]");
    return Array.isArray(value)
      ? value.filter((e): e is PendingPut => !!e && typeof (e as PendingPut).path === "string")
      : [];
  } catch {
    return [];
  }
}

function writeQueue(store: KeyValueStore | null, entries: PendingPut[]): void {
  if (!store) return;
  try {
    if (entries.length === 0) store.removeItem(QUEUE_KEY);
    else store.setItem(QUEUE_KEY, JSON.stringify(entries.slice(-MAX_ENTRIES)));
  } catch {
    // ignore: storage full or disabled
  }
}

/** Adds or replaces (same path: the newer body wins, a correction of the same set). */
export function enqueue(store: KeyValueStore | null, entry: PendingPut): void {
  const entries = readQueue(store).filter((e) => e.path !== entry.path);
  writeQueue(store, [...entries, entry]);
}

export function removeFromQueue(store: KeyValueStore | null, path: string): void {
  writeQueue(
    store,
    readQueue(store).filter((e) => e.path !== path),
  );
}

let flushing: Promise<FlushResult> | null = null;

/**
 * Sends the queue oldest first. Stops at the first retryable failure (the network is still down;
 * the rest would fail too) and keeps it and everything after it. One flush at a time per page.
 */
export function flushQueue(store: KeyValueStore | null, send: Send): Promise<FlushResult> {
  if (flushing) return flushing;
  const run = (async () => {
    const result: FlushResult = { sent: [], dropped: [], remaining: 0 };
    for (const entry of readQueue(store)) {
      const answer = await send(entry.path, entry.body);
      if (answer.ok) {
        result.sent.push(entry.path);
      } else if (!isRetryable(answer.status)) {
        result.dropped.push({ path: entry.path, status: answer.status, error: answer.error });
      } else {
        break;
      }
      removeFromQueue(store, entry.path);
    }
    result.remaining = readQueue(store).length;
    return result;
  })();
  flushing = run;
  const clear = () => {
    if (flushing === run) flushing = null;
  };
  run.then(clear, clear);
  return run;
}
