import type { ReactNode } from "react";

import { buttonVariants } from "@/components/ui/button";

export function Card({
  title,
  action,
  children,
  className = "",
  labelledBy,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  labelledBy?: string;
}) {
  return (
    <section
      aria-labelledby={labelledBy}
      className={`rounded-card border border-border bg-surface p-4 shadow-card sm:p-5 ${className}`}
    >
      {title || action ? (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title ? (
            <h2 id={labelledBy} className="text-sm font-semibold tracking-tight">
              {title}
            </h2>
          ) : null}
          {action}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function PageHeader({
  title,
  subtitle,
  aside,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle ? <div className="mt-1 text-sm text-muted">{subtitle}</div> : null}
      </div>
      {aside ? <div className="shrink-0">{aside}</div> : null}
    </div>
  );
}

export function ErrorState({ title = "Could not load data", message }: { title?: string; message: string }) {
  return (
    <div role="alert" className="rounded-xl border border-bad/30 bg-bad-soft px-4 py-3 text-sm">
      <p className="font-medium text-bad">{title}</p>
      <p className="mt-0.5 text-muted">{message}</p>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border px-4 py-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      {children ? <div className="mt-1 text-sm text-muted">{children}</div> : null}
    </div>
  );
}

export { Skeleton } from "@/components/ui/skeleton";
export { Badge, type Tone } from "@/components/ui/badge";

export function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-card border border-border bg-surface p-4 shadow-card sm:p-5">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight sm:text-3xl">{value}</dd>
      {hint ? <dd className="mt-0.5 text-xs text-muted">{hint}</dd> : null}
    </div>
  );
}

export { controlClass as inputClass } from "@/components/ui/input";

export const buttonClass = buttonVariants({ variant: "primary" });

export const secondaryButtonClass = buttonVariants({ variant: "outline" });
