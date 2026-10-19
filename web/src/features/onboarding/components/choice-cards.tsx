"use client";

import { Check } from "lucide-react";
import { useId } from "react";

import { cn } from "@/lib/cn";

export interface Choice<T extends string> {
  value: T;
  label: string;
  hint?: string;
}

/** A radio group drawn as big tappable cards (native radios: arrow keys and screen readers work). */
export function ChoiceCards<T extends string>({
  legend,
  hint,
  value,
  choices,
  onChange,
  name,
}: {
  legend: string;
  hint?: string;
  value: T;
  choices: readonly Choice<T>[];
  onChange: (value: T) => void;
  name: string;
}) {
  const id = useId();
  return (
    <fieldset className="flex flex-col gap-2" aria-describedby={hint ? `${id}-hint` : undefined}>
      <legend className="mb-2 text-label font-semibold uppercase tracking-[0.08em] text-muted">{legend}</legend>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {choices.map((choice) => {
          const checked = choice.value === value;
          return (
            <label
              key={choice.value}
              className={cn(
                "relative flex min-h-16 cursor-pointer items-center gap-3 rounded-card border-2 bg-surface px-4 py-3 transition has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent",
                checked ? "border-accent bg-accent-soft" : "border-border hover:border-muted",
              )}
            >
              <input
                type="radio"
                name={`${id}-${name}`}
                value={choice.value}
                checked={checked}
                onChange={() => onChange(choice.value)}
                className="sr-only"
              />
              <span className="flex-1">
                <span className="block font-bold">{choice.label}</span>
                {/* Muted grey is too faint on the accent tint of a checked card (axe colour contrast). */}
                {choice.hint ? <span className={cn("block text-sm", checked ? "text-text" : "text-muted")}>{choice.hint}</span> : null}
              </span>
              <span
                aria-hidden
                className={cn(
                  "grid size-6 shrink-0 place-items-center rounded-full border-2",
                  checked ? "border-accent bg-accent text-accent-contrast" : "border-border",
                )}
              >
                {checked ? <Check className="size-4" strokeWidth={3} /> : null}
              </span>
            </label>
          );
        })}
      </div>
      {hint ? (
        <p id={`${id}-hint`} className="text-sm text-muted">
          {hint}
        </p>
      ) : null}
    </fieldset>
  );
}
