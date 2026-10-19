"use client";

import { useEffect } from "react";

/** Registers the service worker in production builds (development keeps no cache). */
export function ServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      // An unsupported or blocked registration only means no offline page.
    });
  }, []);
  return null;
}
