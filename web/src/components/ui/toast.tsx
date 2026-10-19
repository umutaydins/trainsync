"use client";

import { Toast as ToastPrimitive } from "radix-ui";
import { type ReactNode, createContext, useCallback, useContext, useState } from "react";

import { cn } from "@/lib/cn";

type Tone = "ok" | "bad" | "neutral";
interface ToastMessage {
  id: number;
  text: string;
  tone: Tone;
}

const TOAST_MS = 3500;
const ToastContext = createContext<(text: string, tone?: Tone) => void>(() => {});

/**
 * Short confirmations ("Saved", "Set logged"); announced politely to screen readers. Radix also
 * copies the text into a hidden live region, so tests find a toast by `data-testid="toast"`.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const show = useCallback((text: string, tone: Tone = "neutral") => {
    setToasts((current) => [...current, { id: Date.now() + Math.random(), text, tone }]);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      <ToastPrimitive.Provider duration={TOAST_MS} swipeDirection="down">
        {children}
        {toasts.map((toast) => (
          <ToastPrimitive.Root
            key={toast.id}
            data-testid="toast"
            data-tone={toast.tone}
            onOpenChange={(open) => {
              if (!open) setToasts((current) => current.filter((t) => t.id !== toast.id));
            }}
            className={cn(
              "rounded-control border px-4 py-3 text-sm font-medium shadow-float",
              toast.tone === "ok" && "border-ok/30 bg-ok-soft text-ok",
              toast.tone === "bad" && "border-bad/30 bg-bad-soft text-bad",
              toast.tone === "neutral" && "border-border bg-surface text-text",
            )}
          >
            <ToastPrimitive.Description>{toast.text}</ToastPrimitive.Description>
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport className="fixed inset-x-4 bottom-[calc(var(--spacing-tabbar)+env(safe-area-inset-bottom)+0.75rem)] z-[60] flex flex-col gap-2 outline-none md:bottom-6 md:left-auto md:right-6 md:w-96" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export function useToast(): (text: string, tone?: Tone) => void {
  return useContext(ToastContext);
}
