"use client";

import type { ReactNode } from "react";
import { Drawer } from "vaul";

import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useMediaQuery } from "@/components/ui/use-media-query";

/** Wider than this, a sheet is a centred dialog; narrower, a bottom drawer (ADR 0039). */
const DESKTOP_QUERY = "(min-width: 768px)";

/**
 * A bottom sheet on phones (swipe down to close, thumb-reachable), a dialog on desktop. Controlled:
 * the caller owns `open`.
 */
export function ResponsiveSheet({
  open,
  onOpenChange,
  title,
  description,
  closeLabel,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  closeLabel: string;
  children: ReactNode;
}) {
  const desktop = useMediaQuery(DESKTOP_QUERY);
  if (desktop) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent title={title} description={description} closeLabel={closeLabel}>
          {children}
        </DialogContent>
      </Dialog>
    );
  }
  return (
    <Drawer.Root open={open} onOpenChange={onOpenChange}>
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-50 bg-overlay" />
        <Drawer.Content className="fixed inset-x-0 bottom-0 z-50 flex max-h-[92dvh] flex-col rounded-t-sheet border border-border bg-surface pb-[max(1rem,env(safe-area-inset-bottom))] outline-none">
          <div aria-hidden className="mx-auto mt-3 h-1.5 w-12 shrink-0 rounded-full bg-surface-3" />
          <div className="overflow-y-auto px-5 pt-4">
            <Drawer.Title className="text-lg font-semibold tracking-tight">{title}</Drawer.Title>
            {description ? (
              <Drawer.Description className="mt-1 text-sm text-muted">{description}</Drawer.Description>
            ) : null}
            <div className="mt-4">{children}</div>
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
