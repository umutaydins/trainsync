import type { ReactNode } from "react";

export function PageTitle({
  title,
  subtitle,
  aside,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{title}</h1>
        {subtitle ? <div className="mt-1 text-sm text-muted">{subtitle}</div> : null}
      </div>
      {aside ? <div className="shrink-0">{aside}</div> : null}
    </header>
  );
}
