"use client";

import { X } from "lucide-react";
import { Dialog as DialogPrimitive } from "radix-ui";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/cn";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({
  className,
  children,
  title,
  description,
  closeLabel,
  ...props
}: Omit<ComponentProps<typeof DialogPrimitive.Content>, "title"> & {
  title: ReactNode;
  description?: ReactNode;
  closeLabel: string;
}) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-overlay backdrop-blur-sm" />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 max-h-[90dvh] w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-sheet border border-border bg-surface p-6 shadow-float",
          className,
        )}
        {...props}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <DialogPrimitive.Title className="text-lg font-semibold tracking-tight">
              {title}
            </DialogPrimitive.Title>
            {description ? (
              <DialogPrimitive.Description className="mt-1 text-sm text-muted">
                {description}
              </DialogPrimitive.Description>
            ) : null}
          </div>
          <DialogPrimitive.Close
            aria-label={closeLabel}
            className="-m-2 grid size-touch place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-text"
          >
            <X aria-hidden className="size-5" />
          </DialogPrimitive.Close>
        </div>
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
