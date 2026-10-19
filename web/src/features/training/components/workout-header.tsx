"use client";

import { CloudUpload, MonitorSmartphone } from "lucide-react";
import { useTranslations } from "next-intl";

import { formatClock } from "@/lib/format";
import { type SetDraft, elapsedMs } from "@/features/training/timers";
import { useTrainingFormat } from "@/features/training/use-training-format";
import { loggedVolume } from "@/features/training/workout-rows";

const MS_PER_S = 1000;

/** The sticky top of the workout: elapsed time, sets and volume so far, sync and screen state. */
export function WorkoutHeader({
  startedAt,
  clock,
  rows,
  queued,
  screenOn,
}: {
  startedAt: string;
  clock: number;
  rows: SetDraft[];
  queued: number;
  screenOn: boolean;
}) {
  const t = useTranslations("workout.header");
  const fmt = useTrainingFormat();
  const logged = rows.filter((r) => r.status === "saved").length;
  return (
    <div className="sticky top-0 z-20 -mx-4 flex items-center justify-between gap-3 border-b border-border bg-bg/95 px-4 py-2 backdrop-blur sm:mx-0 sm:rounded-card sm:border">
      <div>
        <p className="text-label font-semibold uppercase tracking-[0.08em] text-muted">{t("time")}</p>
        <p className="text-3xl font-black tabular tracking-tight" data-testid="workout-elapsed" aria-live="off">
          {formatClock(elapsedMs(Date.parse(startedAt), clock) / MS_PER_S)}
        </p>
      </div>
      <div className="text-right text-xs text-muted" aria-live="polite">
        <p className="text-sm font-semibold text-text tabular">
          {t("sets", { count: logged })} · {fmt.volume(loggedVolume(rows))}
        </p>
        {queued > 0 ? (
          <p className="inline-flex items-center gap-1 text-warn" data-testid="queued-count">
            <CloudUpload aria-hidden className="size-3.5" />
            {t("queued", { count: queued })}
          </p>
        ) : null}
        {screenOn ? (
          <p className="inline-flex items-center gap-1">
            <MonitorSmartphone aria-hidden className="size-3.5" />
            {t("screenOn")}
          </p>
        ) : null}
      </div>
    </div>
  );
}
