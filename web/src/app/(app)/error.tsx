"use client";

import { useEffect, useState } from "react";

import { ErrorState, secondaryButtonClass } from "@/components/ui";
import { BACKEND_UNREACHABLE_TITLE, BACKEND_UNREACHABLE_TEXT } from "@/lib/backend-copy";

type Reachability = "checking" | "reachable" | "unreachable";

/**
 * Error boundary for the app pages. In production the error's details are hidden from the
 * browser, so it asks the server whether the backend answers at all (P7.6): when it does not,
 * the page explains that the backend is offline instead of a generic failure.
 */
export default function Error({ reset }: { error: Error; reset: () => void }) {
  const [reachability, setReachability] = useState<Reachability>("checking");

  useEffect(() => {
    let cancelled = false;
    fetch("/api/backend-status", { cache: "no-store", credentials: "same-origin" })
      .then((response) => (response.ok ? (response.json() as Promise<{ reachable?: unknown }>) : { reachable: false }))
      .then((body) => !cancelled && setReachability(body.reachable === true ? "reachable" : "unreachable"))
      .catch(() => !cancelled && setReachability("unreachable"));
    return () => {
      cancelled = true;
    };
  }, []);

  const offline = reachability === "unreachable";
  return (
    <div className="space-y-3">
      <ErrorState
        title={offline ? BACKEND_UNREACHABLE_TITLE : "Something went wrong"}
        message={offline ? BACKEND_UNREACHABLE_TEXT : "The page could not be rendered."}
      />
      <button type="button" onClick={reset} className={secondaryButtonClass}>
        Try again
      </button>
    </div>
  );
}
