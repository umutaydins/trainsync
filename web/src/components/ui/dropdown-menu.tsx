"use client";

import { DropdownMenu as Menu } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "@/lib/cn";

export const DropdownMenu = Menu.Root;
export const DropdownMenuTrigger = Menu.Trigger;

export function DropdownMenuContent({ className, ...props }: ComponentProps<typeof Menu.Content>) {
  return (
    <Menu.Portal>
      <Menu.Content
        sideOffset={6}
        className={cn(
          "z-50 min-w-48 rounded-control border border-border bg-surface p-1 shadow-float",
          className,
        )}
        {...props}
      />
    </Menu.Portal>
  );
}

export function DropdownMenuItem({ className, ...props }: ComponentProps<typeof Menu.Item>) {
  return (
    <Menu.Item
      className={cn(
        "flex h-touch cursor-pointer select-none items-center gap-2 rounded-[0.6rem] px-3 text-sm outline-none data-[highlighted]:bg-surface-2",
        className,
      )}
      {...props}
    />
  );
}
