"use client";

import { Bell, ChevronDown, ChevronUp, Minus, Plus, SkipForward } from "lucide-react";
import { useTranslations } from "next-intl";
import { Dialog as DialogPrimitive } from "radix-ui";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ProgressRing } from "@/components/ui/progress-ring";
import { cn } from "@/lib/cn";
import { formatClock } from "@/lib/format";
import { notificationPermission, requestNotifications } from "@/features/training/alerts";
import { type RestTimer, REST_STEP_S, isFinished, remainingSeconds, restProgress } from "@/features/training/timers";

const RING_PX = 264;

interface RestTimerProps {
  rest: RestTimer;
  now: number;
  onAdjust: (deltaS: number) => void;
  onSkip: () => void;
}

/**
 * The rest countdown (renders from `endsAt` and `now`). Full screen while it runs: a ring, the
 * time in big figures, −/+ 15 s and skip within thumb reach. "Hide" (or Escape) shrinks it to a
 * bar above the tab bar so the next set can be prepared; a new rest opens it full screen again.
 */
export function RestTimerPanel(props: RestTimerProps) {
  const [hiddenFor, setHiddenFor] = useState<string | null>(null);
  const hidden = hiddenFor === props.rest.label;
  return hidden ? (
    <RestBar {...props} onShow={() => setHiddenFor(null)} />
  ) : (
    <FullScreenRest {...props} onHide={() => setHiddenFor(props.rest.label)} />
  );
}

function FullScreenRest({ rest, now, onAdjust, onSkip, onHide }: RestTimerProps & { onHide: () => void }) {
  const t = useTranslations("workout.rest");
  const [permission, setPermission] = useState(() => notificationPermission());
  const skipRef = useRef<HTMLButtonElement>(null);
  const done = isFinished(rest, now);
  const left = remainingSeconds(rest, now);

  return (
    <DialogPrimitive.Root open onOpenChange={(open) => !open && onHide()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Content
          data-testid="rest-timer"
          data-remaining={left}
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            skipRef.current?.focus();
          }}
          className="fixed inset-0 z-50 flex flex-col bg-bg px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-[max(1.25rem,env(safe-area-inset-top))] outline-none"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <DialogPrimitive.Title className="text-label font-semibold uppercase tracking-[0.08em] text-muted">
                {done ? t("over") : t("title")}
              </DialogPrimitive.Title>
              <p className="truncate text-sm font-medium">{t("after", { label: rest.label })}</p>
            </div>
            <Button variant="ghost" onClick={onHide}>
              <ChevronDown aria-hidden />
              {t("hide")}
            </Button>
          </div>

          <div className="flex flex-1 items-center justify-center py-6">
            <ProgressRing value={restProgress(rest, now)} size={RING_PX} label={t("progress")}>
              <span className={cn("block text-7xl font-black tabular tracking-tight", done && "text-ok")} data-testid="rest-remaining">
                {formatClock(left)}
              </span>
            </ProgressRing>
          </div>
          <p className="sr-only" aria-live="assertive">
            {done ? t("over") : ""}
          </p>

          <div className="mx-auto flex w-full max-w-md flex-col gap-3">
            <div className="grid grid-cols-2 gap-3">
              <Button variant="secondary" size="lg" onClick={() => onAdjust(-REST_STEP_S)} aria-label={t("less", { seconds: REST_STEP_S })}>
                <Minus aria-hidden />
                {t("step", { seconds: REST_STEP_S })}
              </Button>
              <Button variant="secondary" size="lg" onClick={() => onAdjust(REST_STEP_S)} aria-label={t("more", { seconds: REST_STEP_S })}>
                <Plus aria-hidden />
                {t("step", { seconds: REST_STEP_S })}
              </Button>
            </div>
            <Button ref={skipRef} size="lg" block onClick={onSkip} className="h-16 text-lg">
              <SkipForward aria-hidden />
              {done ? t("done") : t("skip")}
            </Button>
            {permission === "default" ? (
              <Button variant="ghost" block onClick={async () => setPermission(await requestNotifications())}>
                <Bell aria-hidden />
                {t("notify")}
              </Button>
            ) : null}
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function RestBar({ rest, now, onSkip, onShow }: RestTimerProps & { onShow: () => void }) {
  const t = useTranslations("workout.rest");
  const done = isFinished(rest, now);
  const left = remainingSeconds(rest, now);
  return (
    <div
      role="region"
      aria-label={t("title")}
      data-testid="rest-timer"
      data-remaining={left}
      className="fixed inset-x-3 bottom-[calc(var(--spacing-tabbar)+env(safe-area-inset-bottom)+0.5rem)] z-30 flex items-center gap-2 rounded-card border border-border bg-surface p-2 pl-4 shadow-float md:inset-x-auto md:bottom-6 md:right-6 md:w-96"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs text-muted">{done ? t("over") : t("after", { label: rest.label })}</p>
        <p className={cn("text-2xl font-black tabular", done && "text-ok")} data-testid="rest-remaining">
          {formatClock(left)}
        </p>
      </div>
      <Button variant="secondary" size="icon" onClick={onShow} aria-label={t("show")}>
        <ChevronUp aria-hidden />
      </Button>
      <Button onClick={onSkip}>{done ? t("done") : t("skip")}</Button>
    </div>
  );
}
