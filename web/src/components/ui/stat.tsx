import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** A big confident number with its label, unit and change (stat cards, ADR 0039). */
export function Stat({
  label,
  value,
  unit,
  change,
  hint,
  className,
  size = "stat",
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  change?: ReactNode;
  hint?: ReactNode;
  className?: string;
  size?: "stat" | "hero";
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <dt className="text-label font-semibold uppercase tracking-[0.08em] text-muted">{label}</dt>
      <dd className="flex flex-wrap items-baseline gap-x-1.5 gap-y-1">
        <span
          className={cn(
            "font-semibold tracking-tight tabular",
            size === "hero" ? "text-hero" : "text-stat",
          )}
        >
          {value}
        </span>
        {unit ? <span className="text-sm font-medium text-muted">{unit}</span> : null}
        {change}
      </dd>
      {hint ? <dd className="text-xs text-muted">{hint}</dd> : null}
    </div>
  );
}
