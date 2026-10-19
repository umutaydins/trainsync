import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { cn } from "@/lib/cn";

/** Which direction is good news for a number (more distance: up; slower pace: down). */
export type Better = "up" | "down" | "neither";

/**
 * ▲▼ change against the previous period. `label` is the screen-reader text the caller builds
 * (e.g. "up 12% vs previous period"); `text` is what is shown (e.g. "12%").
 */
export function ChangeBadge({
  pct,
  text,
  label,
  better = "up",
  className,
}: {
  pct: number | null | undefined;
  text: string;
  label: string;
  better?: Better;
  className?: string;
}) {
  if (pct == null) return null;
  const direction = pct > 0 ? "up" : pct < 0 ? "down" : "same";
  const good = better !== "neither" && direction === better;
  const bad = better !== "neither" && direction !== "same" && direction !== better;
  const Icon = direction === "up" ? ArrowUpRight : direction === "down" ? ArrowDownRight : Minus;
  return (
    <span
      aria-label={label}
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-semibold tabular",
        good ? "bg-ok-soft text-ok" : bad ? "bg-bad-soft text-bad" : "bg-surface-2 text-muted",
        className,
      )}
    >
      <Icon aria-hidden className="size-3.5" />
      <span aria-hidden>{text}</span>
    </span>
  );
}
