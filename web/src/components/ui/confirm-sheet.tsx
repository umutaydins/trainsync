"use client";

import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { ResponsiveSheet } from "@/components/ui/sheet";

/**
 * "Are you sure?" for a destructive action: a bottom sheet on phones, a dialog on desktop, the
 * confirm button at the bottom for the thumb. `children` can add fields (a password, a typed word);
 * `canConfirm` gates the button on them.
 */
export function ConfirmSheet({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel,
  closeLabel,
  busy = false,
  canConfirm = true,
  error,
  onConfirm,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  closeLabel: string;
  busy?: boolean;
  canConfirm?: boolean;
  error?: ReactNode;
  onConfirm: () => void;
  children?: ReactNode;
}) {
  return (
    <ResponsiveSheet open={open} onOpenChange={onOpenChange} title={title} description={description} closeLabel={closeLabel}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (canConfirm && !busy) onConfirm();
        }}
      >
        {children}
        {error ? (
          <p role="alert" className="rounded-control bg-bad-soft px-4 py-3 text-sm font-medium text-bad">
            {error}
          </p>
        ) : null}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="secondary" size="lg" className="sm:h-touch sm:text-sm" onClick={() => onOpenChange(false)}>
            {cancelLabel}
          </Button>
          <Button type="submit" variant="danger" size="lg" className="sm:h-touch sm:text-sm" disabled={busy || !canConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </form>
    </ResponsiveSheet>
  );
}
