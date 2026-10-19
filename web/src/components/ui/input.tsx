import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const controlClass =
  "block h-touch w-full rounded-control border border-border bg-surface-2 px-3.5 text-base text-text outline-none transition placeholder:text-muted focus:border-accent focus:ring-2 focus:ring-accent/40 aria-invalid:border-bad disabled:opacity-60 sm:text-sm";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input data-slot="input" className={cn(controlClass, className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(controlClass, "h-auto min-h-24 py-2.5", className)}
      {...props}
    />
  );
}

/** A native select: the phone's own picker, keyboard-accessible everywhere. */
export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select data-slot="select" className={cn(controlClass, "pr-8", className)} {...props} />;
}
