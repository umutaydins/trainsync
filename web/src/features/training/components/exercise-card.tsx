"use client";

import { Disc3, Plus } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SetRow } from "@/features/training/components/set-row";
import { readNumber } from "@/features/training/steps";
import type { SetDraft } from "@/features/training/timers";
import { useTrainingFormat } from "@/features/training/use-training-format";
import type { ExerciseGroup } from "@/features/training/workout-rows";

/** Plates for the next set to do, else the last weight entered (0: nothing to load yet). */
export function plateTarget(rows: SetDraft[]): number {
  const next = rows.find((r) => r.status !== "saved" && readNumber(r.weightKg) > 0);
  const lastEntered = [...rows].reverse().find((r) => readNumber(r.weightKg) > 0);
  return readNumber((next ?? lastEntered)?.weightKg ?? "");
}

/** One exercise of the workout: the plan, last time and the suggestion, then its sets. */
export function ExerciseCard({
  group,
  currentId,
  onChange,
  onLog,
  onAddSet,
  onPlates,
}: {
  group: ExerciseGroup;
  /** The client id of the set to do next (shown big), if it is in this exercise. */
  currentId: string | null;
  onChange: (clientId: string, change: Partial<SetDraft>) => void;
  onLog: (row: SetDraft) => void;
  onAddSet: () => void;
  onPlates: (kg: number) => void;
}) {
  const t = useTranslations("workout.exercise");
  const fmt = useTrainingFormat();
  const planned = group.planned;
  const headingId = `exercise-${group.exerciseId}`;
  const plateKg = plateTarget(group.rows);
  const last = planned?.last_performance?.sets ?? [];
  const reps = planned ? (planned.rep_min === planned.rep_max ? String(planned.rep_min) : `${planned.rep_min}–${planned.rep_max}`) : "";

  return (
    <Card aria-labelledby={headingId} data-exercise-id={group.exerciseId} className="p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id={headingId} className="text-xl font-bold tracking-tight">
            {group.name}
          </h2>
          <p className="text-sm text-muted">
            {planned ? t("plan", { sets: planned.sets, reps, rest: group.restSeconds }) : t("restOnly", { rest: group.restSeconds })}
          </p>
          {planned?.suggestion.weight_kg != null ? (
            <p className="mt-1 text-sm" data-testid="suggestion">
              {t("suggested")} <span className="font-semibold text-accent-ink">{fmt.kg(planned.suggestion.weight_kg)}</span>
              <span className="text-muted"> · {t(`why.${planned.suggestion.action}`)}</span>
            </p>
          ) : null}
        </div>
        {group.equipment === "barbell" && plateKg > 0 ? (
          <Button variant="outline" className="shrink-0" onClick={() => onPlates(plateKg)}>
            <Disc3 aria-hidden />
            {t("plates")}
          </Button>
        ) : null}
      </div>
      <ol className="flex flex-col gap-2">
        {group.rows.map((row) => (
          <SetRow
            key={row.clientId}
            name={group.name}
            equipment={group.equipment}
            row={row}
            last={last[row.setIndex - 1]}
            planned={planned !== null}
            current={row.clientId === currentId}
            onChange={(change) => onChange(row.clientId, change)}
            onLog={() => onLog(row)}
          />
        ))}
      </ol>
      <Button variant="ghost" className="mt-2 text-accent-ink" onClick={onAddSet}>
        <Plus aria-hidden />
        {t("addSet")}
      </Button>
    </Card>
  );
}
