"use client";

import { useEffect, useState } from "react";

import { PlateBar } from "@/components/training/plate-bar";
import { Sheet } from "@/components/training/sheet";
import { ErrorState, Skeleton } from "@/components/ui";
import { bffGet } from "@/lib/bff-get";
import type { PlatesOut } from "@/lib/training-types";
import { formatKg } from "@/lib/training-types";

/** Plate calculator for one target weight, answered by `GET /v1/training/plates`. */
export function PlateSheet({ targetKg, exerciseName, onClose }: { targetKg: number; exerciseName: string; onClose: () => void }) {
  const [state, setState] = useState<{ target: number; answer?: PlatesOut; error?: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void bffGet<PlatesOut>("/v1/training/plates", { target: targetKg }, { signal: controller.signal }).then((result) => {
      if (controller.signal.aborted) return;
      setState(result.ok && result.data ? { target: targetKg, answer: result.data } : { target: targetKg, error: result.ok ? "empty answer" : result.error });
    });
    return () => controller.abort();
  }, [targetKg]);

  const current = state?.target === targetKg ? state : null;
  return (
    <Sheet title={`Plates for ${formatKg(targetKg)}`} onClose={onClose}>
      <p className="mb-3 text-sm text-muted">{exerciseName}</p>
      {current?.answer ? (
        <PlateBar answer={current.answer} />
      ) : current?.error ? (
        <ErrorState title="Could not work out the plates" message={current.error} />
      ) : (
        <Skeleton className="h-32 w-full" label="Loading plates" />
      )}
    </Sheet>
  );
}
