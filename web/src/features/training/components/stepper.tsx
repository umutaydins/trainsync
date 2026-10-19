"use client";

import { Minus, Plus } from "lucide-react";
import { useId } from "react";

import { Button } from "@/components/ui/button";
import { stepped } from "@/features/training/steps";

/**
 * A number with huge − and + buttons (64 px, ADR 0039) for one-handed use in the gym. The value
 * stays typeable in between; each tap moves it by `step` within `min`..`max`.
 */
export function Stepper({
  label,
  value,
  onChange,
  step,
  min,
  max,
  grid,
  inputMode,
  inputLabel,
  decreaseLabel,
  increaseLabel,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  step: number;
  min: number;
  max: number;
  /** Values snap to multiples of this (the API's 0.25 kg, whole reps). */
  grid: number;
  inputMode: "numeric" | "decimal";
  /** The input's spoken name, with the exercise and set ("Weight in kg, Bench Press set 1"). */
  inputLabel: string;
  decreaseLabel: string;
  increaseLabel: string;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div role="group" aria-labelledby={id} className="flex flex-col gap-1.5">
      <span id={id} className="text-label font-semibold uppercase tracking-[0.08em] text-muted">
        {label}
      </span>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="secondary"
          size="stepper"
          aria-label={decreaseLabel}
          disabled={disabled}
          onClick={() => onChange(stepped(value, -step, { min, max, grid }))}
        >
          <Minus aria-hidden />
        </Button>
        <input
          inputMode={inputMode}
          value={value}
          aria-label={inputLabel}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="h-16 w-full min-w-0 flex-1 rounded-card border border-border bg-surface-2 text-center text-3xl font-bold tabular tracking-tight outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/40"
        />
        <Button
          type="button"
          variant="secondary"
          size="stepper"
          aria-label={increaseLabel}
          disabled={disabled}
          onClick={() => onChange(stepped(value, step, { min, max, grid }))}
        >
          <Plus aria-hidden />
        </Button>
      </div>
    </div>
  );
}
