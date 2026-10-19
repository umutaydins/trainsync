"use client";

import { Check } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { DURATION } from "@/lib/motion";
import { Stepper } from "@/features/training/components/stepper";
import { REPS_STEP, weightStep } from "@/features/training/steps";
import type { SetDraft } from "@/features/training/timers";
import type { components } from "@/lib/api-types";
import { useTrainingFormat } from "@/features/training/use-training-format";
import { SET_LIMITS } from "@/features/training/workout-rows";

type PerformedSet = components["schemas"]["PerformedSet"];

/** The check pops in when a set is logged; with reduced motion it just appears. */
const POP_FROM = 0.6;

/**
 * One set of an exercise. The current set (the next one to do) is big: −/+ steppers for weight and
 * reps and a one-tap "Set done". The others are compact, still editable and tappable.
 */
export function SetRow({
  name,
  equipment,
  row,
  last,
  planned,
  current,
  onChange,
  onLog,
}: {
  name: string;
  equipment: string;
  row: SetDraft;
  /** The same set of the last session of this exercise. */
  last: PerformedSet | undefined;
  planned: boolean;
  current: boolean;
  onChange: (change: Partial<SetDraft>) => void;
  onLog: () => void;
}) {
  const t = useTranslations("workout.set");
  const fmt = useTrainingFormat();
  const saved = row.status === "saved";
  const names = { name, index: row.setIndex };
  const hint = last ? t("last", { reps: last.reps, weight: fmt.kg(last.weight_kg) }) : planned ? t("lastNone") : null;
  const status = row.status === "error" && row.error ? t(`errors.${row.error}`) : row.status === "idle" || row.status === "error" ? "" : t(`status.${row.status}`);

  return (
    <li
      data-testid="set-row"
      data-status={row.status}
      data-client-id={row.clientId}
      className={cn(
        "rounded-card border p-3 transition-colors",
        saved ? "border-ok/40 bg-ok-soft" : current ? "border-accent/50 bg-surface-2/40" : "border-border",
      )}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
        <span className={cn("font-bold tabular", current ? "text-lg" : "text-sm")}>{t("number", { index: row.setIndex })}</span>
        {hint ? <span className="text-xs text-muted">{hint}</span> : null}
      </div>
      {current ? (
        <CurrentSet equipment={equipment} row={row} names={names} onChange={onChange} onLog={onLog} />
      ) : (
        <CompactSet row={row} names={names} onChange={onChange} onLog={onLog} />
      )}
      <p role="status" className={cn("mt-1 min-h-4 text-xs", row.status === "error" ? "text-bad" : row.status === "queued" ? "text-warn" : "text-muted")}>
        {status}
      </p>
    </li>
  );
}

type Names = { name: string; index: number };

function CurrentSet({ equipment, row, names, onChange, onLog }: { equipment: string; row: SetDraft; names: Names; onChange: (change: Partial<SetDraft>) => void; onLog: () => void }) {
  const t = useTranslations("workout.set");
  return (
    <div className="mt-3 flex flex-col gap-3">
      <Stepper
        label={t("weight")}
        value={row.weightKg}
        onChange={(weightKg) => onChange({ weightKg })}
        step={weightStep(equipment)}
        min={SET_LIMITS.weight.min}
        max={SET_LIMITS.weight.max}
        grid={SET_LIMITS.weight.step}
        inputMode="decimal"
        inputLabel={t("weightLabel", names)}
        decreaseLabel={t("lessWeight", names)}
        increaseLabel={t("moreWeight", names)}
      />
      <Stepper
        label={t("reps")}
        value={row.reps}
        onChange={(reps) => onChange({ reps })}
        step={REPS_STEP}
        min={SET_LIMITS.reps.min}
        max={SET_LIMITS.reps.max}
        grid={REPS_STEP}
        inputMode="numeric"
        inputLabel={t("repsLabel", names)}
        decreaseLabel={t("fewerReps", names)}
        increaseLabel={t("moreReps", names)}
      />
      <Button size="lg" block onClick={onLog} disabled={row.status === "saving"} aria-label={t("log", names)} className="h-16 text-lg">
        <Check aria-hidden strokeWidth={3} />
        {t("done")}
      </Button>
    </div>
  );
}

function CompactSet({ row, names, onChange, onLog }: { row: SetDraft; names: Names; onChange: (change: Partial<SetDraft>) => void; onLog: () => void }) {
  const t = useTranslations("workout.set");
  const reduce = useReducedMotion();
  const saved = row.status === "saved";
  const field = "h-12 w-full min-w-0 rounded-control border border-border bg-surface px-2 text-center text-lg tabular outline-none focus:border-accent focus:ring-2 focus:ring-accent/40";
  return (
    <div className="mt-2 flex items-center gap-2">
      <input inputMode="numeric" value={row.reps} aria-label={t("repsLabel", names)} onChange={(e) => onChange({ reps: e.target.value })} className={field} />
      <span aria-hidden className="text-muted">
        ×
      </span>
      <input inputMode="decimal" value={row.weightKg} aria-label={t("weightLabel", names)} onChange={(e) => onChange({ weightKg: e.target.value })} className={field} />
      <span aria-hidden className="text-xs text-muted">
        {t("kg")}
      </span>
      <Button
        variant={saved ? "secondary" : "primary"}
        onClick={onLog}
        aria-label={saved ? t("update", names) : t("log", names)}
        aria-pressed={saved}
        disabled={row.status === "saving"}
        className={cn("h-12 w-14 shrink-0 rounded-control", saved && "bg-ok text-white hover:bg-ok")}
      >
        <motion.span
          key={saved ? "saved" : "open"}
          initial={reduce || !saved ? false : { scale: POP_FROM, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: DURATION.base }}
          className="grid place-items-center"
        >
          <Check aria-hidden strokeWidth={3} />
        </motion.span>
      </Button>
    </div>
  );
}
