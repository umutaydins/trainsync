"use client";

import { Play } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { isBackendDown } from "@/features/shell/components/load-failed";
import { put, type MutationResult } from "@/lib/mutate";
import type { WorkoutDetail } from "@/features/training/types";

type Send = (path: string, body: unknown) => Promise<MutationResult<WorkoutDetail>>;

const defaultSend: Send = (path, body) => put<WorkoutDetail>(path, body);

/**
 * Starts a workout (from a program day, or empty) and opens the workout screen.
 *
 * The start is an idempotent `PUT /v1/training/workouts/{client_id}` (ADR 0017). One client id is
 * created per start and kept until it succeeds, so a double tap or a retry after a lost answer
 * returns the same workout instead of starting a second one.
 */
export function StartWorkoutButton({
  programDayId,
  label,
  busyLabel,
  secondary = false,
  size = "md",
  block = false,
  send = defaultSend,
  newId = () => crypto.randomUUID(),
}: {
  programDayId?: number;
  label: string;
  /** Shown while the start is in flight (pages with translations pass their own). */
  busyLabel?: string;
  secondary?: boolean;
  size?: "md" | "lg";
  block?: boolean;
  /** Test seams. */
  send?: Send;
  newId?: () => string;
}) {
  const t = useTranslations("training.start");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<"failed" | "offline" | null>(null);
  const clientId = useRef<string | null>(null);
  // State updates land after the click handler, so a double tap needs a synchronous guard.
  const inFlight = useRef(false);

  async function start() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    clientId.current ??= newId();
    const body = programDayId ? { program_day_id: programDayId } : {};
    const result = await send(`/v1/training/workouts/${clientId.current}`, body);
    if (result.ok && result.data) {
      router.push(`/training/workout/${result.data.id}`);
      return;
    }
    inFlight.current = false;
    setBusy(false);
    setError(!result.ok && isBackendDown(result.status) ? "offline" : "failed");
  }

  return (
    <div className={block ? "w-full" : undefined}>
      <Button variant={secondary ? "secondary" : "primary"} size={size} block={block} onClick={() => void start()} disabled={busy}>
        <Play aria-hidden />
        {busy ? (busyLabel ?? t("starting")) : label}
      </Button>
      {error ? (
        <p role="alert" className="mt-1.5 text-sm text-bad">
          {t(error)}
        </p>
      ) : null}
    </div>
  );
}
