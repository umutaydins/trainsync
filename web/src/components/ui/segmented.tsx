"use client";

import { ToggleGroup } from "radix-ui";
import { type ComponentType, useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  /** The spoken name when `label` is an abbreviation ("M" → "This month"). */
  ariaLabel?: string;
  /** Shown before the label; with `iconOnPhone`, instead of it below `sm` (the label stays spoken). */
  icon?: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  iconOnPhone?: boolean;
}

/** Fade width at a scrollable edge: says "more this way" without clipping a label mid-word. */
const FADE = "1.25rem";

function fadeMask(start: boolean, end: boolean): string | undefined {
  if (!start && !end) return undefined;
  // A mask only reads alpha: `black` is "shown", whatever the theme.
  const left = start ? `transparent 0, black ${FADE}` : "black 0";
  const right = end ? `black calc(100% - ${FADE}), transparent 100%` : "black 100%";
  return `linear-gradient(to right, ${left}, ${right})`;
}

/**
 * A single choice among a few options (the period switcher): arrow keys move, one is always on.
 * When the options do not fit (a narrow phone, large text) the row scrolls sideways with snap,
 * fades at the edge that has more, and keeps the chosen option in view.
 */
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
  const root = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ start: false, end: false });

  const measure = useCallback(() => {
    const el = root.current;
    if (!el) return;
    const start = el.scrollLeft > 1;
    const end = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
    setEdges((current) => (current.start === start && current.end === end ? current : { start, end }));
  }, []);

  useEffect(() => {
    const el = root.current;
    const active = el?.querySelector<HTMLElement>('[data-state="on"]');
    if (el && active && el.scrollWidth > el.clientWidth) {
      const left = active.offsetLeft - (el.clientWidth - active.offsetWidth) / 2;
      el.scrollLeft = Math.max(0, Math.min(left, el.scrollWidth - el.clientWidth));
    }
    measure();
  }, [value, measure]);

  useEffect(() => {
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  const mask = fadeMask(edges.start, edges.end);
  return (
    <ToggleGroup.Root
      ref={root}
      type="single"
      value={value}
      aria-label={label}
      onValueChange={(next) => {
        if (next) onChange(next as T);
      }}
      onScroll={measure}
      data-overflow={edges.start || edges.end ? "" : undefined}
      style={mask ? { maskImage: mask, WebkitMaskImage: mask } : undefined}
      className={cn(
        "relative flex w-full snap-x snap-proximity scroll-px-1 gap-0.5 overflow-x-auto rounded-full border border-border bg-surface p-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        className,
      )}
    >
      {options.map(({ value: option, label: text, ariaLabel, icon: Icon, iconOnPhone }) => (
        <ToggleGroup.Item
          key={option}
          value={option}
          aria-label={ariaLabel ?? (Icon && iconOnPhone ? text : undefined)}
          className="inline-flex h-9 min-w-10 flex-1 shrink-0 snap-start items-center justify-center gap-1.5 whitespace-nowrap rounded-full px-2 text-sm font-semibold text-muted transition data-[state=on]:bg-accent data-[state=on]:text-accent-contrast sm:px-3"
        >
          {Icon ? <Icon aria-hidden className="size-4 shrink-0" /> : null}
          <span className={cn(Icon && iconOnPhone && "sr-only sm:not-sr-only")}>{text}</span>
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}
