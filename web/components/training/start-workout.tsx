"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { buttonClass, secondaryButtonClass } from "@/components/ui";
import { put, type MutationResult } from "@/lib/mutate";
import type { WorkoutDetail } from "@/lib/training-types";

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
  secondary = false,
  send = defaultSend,
  newId = () => crypto.randomUUID(),
}: {
  programDayId?: number;
  label: string;
  secondary?: boolean;
  /** Test seams. */
  send?: Send;
  newId?: () => string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
    setError(`${result.ok ? "No answer from the API" : result.error}. Tap again to retry.`);
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => void start()}
        disabled={busy}
        className={`${secondary ? secondaryButtonClass : buttonClass} min-h-11 w-full sm:w-auto`}
      >
        {busy ? "Starting…" : label}
      </button>
      {error ? (
        <p role="alert" className="mt-1 text-xs text-bad">
          {error}
        </p>
      ) : null}
    </div>
  );
}
