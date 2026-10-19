"use client";


import { Label } from "radix-ui";
import type { ReactElement, ReactNode } from "react";
import { cloneElement, useId } from "react";

import { cn } from "@/lib/cn";

/**
 * A label, one control and an optional hint or error, wired with ids (`aria-describedby`,
 * `aria-invalid`). The control is the only child.
 */
export function Field({
  label,
  hint,
  error,
  className,
  children,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  className?: string;
  children: ReactElement<Record<string, unknown>>;
}) {
  const id = useId();
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Label.Root htmlFor={id} className="text-sm font-medium">
        {label}
      </Label.Root>
      {cloneElement(children, {
        id,
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : undefined,
      })}
      {error ? (
        <p id={`${id}-error`} className="text-sm text-bad">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-sm text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
