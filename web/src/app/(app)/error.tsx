"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Failure } from "@/components/ui/states";

type Reachability = "checking" | "reachable" | "unreachable";

/**
 * Error boundary for the app pages. In production the error's details are hidden from the
 * browser, so it asks the server whether the backend answers at all (P7.6): when it does not,
 * the page explains that the backend is offline instead of a generic failure.
 */
export default function Error({ reset }: { error: Error; reset: () => void }) {
  const [reachability, setReachability] = useState<Reachability>("checking");
  const t = useTranslations("common");

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
    <Failure
      title={offline ? t("states.backendDownTitle") : t("states.errorTitle")}
      message={offline ? t("states.backendDown") : undefined}
      action={
        <Button variant="secondary" onClick={reset}>
          {t("actions.retry")}
        </Button>
      }
    />
  );
}
