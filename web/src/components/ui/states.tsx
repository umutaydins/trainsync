import { CircleAlert, Inbox } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export function Empty({
  title,
  children,
  action,
  className,
  titleAs: Title = "p",
}: {
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
  /** `h1` when the empty state is the whole page (the not-found page), so the page has a heading. */
  titleAs?: "p" | "h1" | "h2";
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-card border border-dashed border-border px-6 py-10 text-center",
        className,
      )}
    >
      <Inbox aria-hidden className="size-8 text-muted" />
      <Title className="font-semibold">{title}</Title>
      {children ? <div className="max-w-sm text-sm text-muted">{children}</div> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function Failure({
  title,
  message,
  action,
}: {
  title: ReactNode;
  message?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div role="alert" className="flex gap-3 rounded-card border border-bad/30 bg-bad-soft p-4 text-sm">
      <CircleAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-bad" />
      <div className="flex-1">
        <p className="font-semibold text-bad">{title}</p>
        {message ? <p className="mt-0.5 text-muted">{message}</p> : null}
        {action ? <div className="mt-3">{action}</div> : null}
      </div>
    </div>
  );
}
