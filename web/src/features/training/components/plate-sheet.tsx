"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { ResponsiveSheet } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { LoadFailed } from "@/features/shell/components/load-failed";
import { PlateBar } from "@/features/training/components/plate-bar";
import type { PlatesOut } from "@/features/training/types";
import { useTrainingFormat } from "@/features/training/use-training-format";
import { bffGet } from "@/lib/bff-get";

/** An empty answer is not a refusal; it shows like one without the "backend down" note. */
const EMPTY_ANSWER = 200;

/**
 * The plate calculator for one target weight (`GET /v1/training/plates`), as a bottom sheet on
 * phones (over the running rest timer bar) and a dialog on desktop.
 */
export function PlateSheet({ target, onClose }: { target: { kg: number; name: string } | null; onClose: () => void }) {
  const t = useTranslations("workout.plates");
  const common = useTranslations("common.actions");
  const fmt = useTrainingFormat();
  const [state, setState] = useState<{ kg: number; answer?: PlatesOut; status?: number } | null>(null);
  const targetKg = target?.kg ?? null;

  useEffect(() => {
    if (targetKg === null) return;
    const controller = new AbortController();
    void bffGet<PlatesOut>("/v1/training/plates", { target: targetKg }, { signal: controller.signal }).then((result) => {
      if (controller.signal.aborted) return;
      setState(result.ok && result.data ? { kg: targetKg, answer: result.data } : { kg: targetKg, status: result.ok ? EMPTY_ANSWER : result.status });
    });
    return () => controller.abort();
  }, [targetKg]);

  const current = state?.kg === targetKg ? state : null;
  return (
    <ResponsiveSheet
      open={target !== null}
      onOpenChange={(open) => !open && onClose()}
      title={target ? t("title", { weight: fmt.kg(target.kg) }) : ""}
      description={target?.name}
      closeLabel={common("close")}
    >
      {current?.answer ? (
        <PlateBar answer={current.answer} />
      ) : current?.status !== undefined ? (
        <LoadFailed title={t("failed")} status={current.status} />
      ) : (
        <Skeleton className="h-32 w-full" label={t("loading")} />
      )}
      <Button variant="secondary" size="lg" block className="mt-5" onClick={onClose}>
        {common("done")}
      </Button>
    </ResponsiveSheet>
  );
}
