import { cn } from "@/lib/cn";

/** A placeholder block while data loads (never a spinner, ADR 0039). `label` makes it a status. */
export function Skeleton({
  className,
  label,
  height,
}: {
  className?: string;
  label?: string;
  height?: number;
}) {
  return (
    <div
      style={height ? { height } : undefined}
      role={label ? "status" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn("animate-pulse rounded-control bg-surface-2", className)}
    />
  );
}
