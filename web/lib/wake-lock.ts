"use client";

import { useEffect, useState } from "react";

/** `idle`: no lock (not requested yet, released, or the API is missing). */
export type WakeLockStatus = "idle" | "active" | "denied";

interface WakeLockSentinelLike {
  released: boolean;
  release(): Promise<void>;
  addEventListener(type: "release", listener: () => void): void;
}

interface WakeLockLike {
  request(type: "screen"): Promise<WakeLockSentinelLike>;
}

function wakeLockApi(): WakeLockLike | null {
  if (typeof navigator === "undefined") return null;
  const api = (navigator as Navigator & { wakeLock?: WakeLockLike }).wakeLock;
  return api && typeof api.request === "function" ? api : null;
}

/**
 * Keeps the screen on while `active` (Screen Wake Lock API). The browser drops the lock when the
 * tab is hidden, so it is requested again when the page becomes visible. Unsupported or denied
 * (low battery, iframe policy) is not an error: the status says so and nothing else happens.
 */
export function useWakeLock(active: boolean): WakeLockStatus {
  // Same initial value on the server and the client (no hydration difference).
  const [status, setStatus] = useState<WakeLockStatus>("idle");

  useEffect(() => {
    const api = wakeLockApi();
    if (!active || !api) return;
    let sentinel: WakeLockSentinelLike | null = null;
    let cancelled = false;

    async function acquire() {
      if (!api || document.visibilityState !== "visible" || (sentinel && !sentinel.released)) return;
      try {
        const lock = await api.request("screen");
        if (cancelled) {
          void lock.release().catch(() => undefined);
          return;
        }
        sentinel = lock;
        setStatus("active");
        lock.addEventListener("release", () => {
          if (!cancelled) setStatus("idle");
        });
      } catch {
        if (!cancelled) setStatus("denied");
      }
    }

    const onVisible = () => void acquire();
    void acquire();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
      if (sentinel && !sentinel.released) void sentinel.release().catch(() => undefined);
    };
  }, [active]);

  return status;
}
