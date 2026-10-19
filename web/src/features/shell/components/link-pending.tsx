"use client";

import { useLinkStatus } from "next/link";

import { cn } from "@/lib/cn";

/**
 * A thin accent bar under a navigation link while its page loads. The tab roots have no
 * route-level skeleton (it delayed the first paint on slow phones, ADR 0039), so this is the
 * feedback between a tap and the next page.
 */
export function LinkPending({ className }: { className?: string }) {
  const { pending } = useLinkStatus();
  return (
    <span
      aria-hidden
      className={cn(
        "pointer-events-none absolute inset-x-3 bottom-1 h-0.5 rounded-full bg-accent transition-opacity duration-150",
        pending ? "animate-pulse opacity-100" : "opacity-0",
        className,
      )}
    />
  );
}
