"use client";

import { ToggleGroup } from "radix-ui";

import { cn } from "@/lib/cn";

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  /** The spoken name when `label` is an abbreviation ("M" → "This month"). */
  ariaLabel?: string;
}

/** A single choice among a few options (the period switcher): arrow keys move, one is always on. */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  className,
}: {
  value: T;
  options: readonly SegmentOption<T>[];
  onChange: (value: T) => void;
  label: string;
  className?: string;
}) {
  return (
    <ToggleGroup.Root
      type="single"
      value={value}
      aria-label={label}
      onValueChange={(next) => {
        if (next) onChange(next as T);
      }}
      className={cn(
        "flex w-full gap-1 overflow-x-auto rounded-full border border-border bg-surface p-1",
        className,
      )}
    >
      {options.map((option) => (
        <ToggleGroup.Item
          key={option.value}
          value={option.value}
          aria-label={option.ariaLabel}
          className="h-9 min-w-11 flex-1 whitespace-nowrap rounded-full px-3 text-sm font-semibold text-muted transition data-[state=on]:bg-accent data-[state=on]:text-accent-contrast"
        >
          {option.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}
