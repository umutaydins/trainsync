"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { buttonClass, secondaryButtonClass } from "@/components/ui";
import { post } from "@/lib/mutate";
import type { WorkoutDetail } from "@/lib/training-types";

/** Starts a workout (from a program day, or empty) and opens the workout screen. */
export function StartWorkoutButton({
  programDayId,
  label,
  secondary = false,
}: {
  programDayId?: number;
  label: string;
  secondary?: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    if (busy) return;
    setBusy(true);
    setError(null);
    const result = await post<WorkoutDetail>("/v1/training/workouts", programDayId ? { program_day_id: programDayId } : {});
    if (result.ok && result.data) {
      router.push(`/training/workout/${result.data.id}`);
      return;
    }
    setBusy(false);
    setError(result.ok ? "No answer from the API" : result.error);
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
