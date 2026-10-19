import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export function Card({ className, ...props }: ComponentProps<"section">) {
  return (
    <section
      data-slot="card"
      className={cn("rounded-card border border-border bg-surface p-4 shadow-card sm:p-5", className)}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("mb-3 flex items-center justify-between gap-3", className)} {...props} />;
}

export function CardTitle({ className, ...props }: ComponentProps<"h2">) {
  return (
    <h2
      className={cn("text-label font-semibold uppercase tracking-[0.08em] text-muted", className)}
      {...props}
    />
  );
}
