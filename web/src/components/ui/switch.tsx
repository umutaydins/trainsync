"use client";

import { Switch as SwitchPrimitive } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export function Switch({ className, ...props }: ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        "relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center rounded-full border border-border bg-surface-3 transition data-[state=checked]:border-accent data-[state=checked]:bg-accent disabled:opacity-50",
        // A 44 px hit area around the 28 px track.
        "before:absolute before:-inset-2 before:content-['']",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb className="block size-5 translate-x-1 rounded-full bg-text shadow transition-transform data-[state=checked]:translate-x-6 data-[state=checked]:bg-accent-contrast" />
    </SwitchPrimitive.Root>
  );
}
