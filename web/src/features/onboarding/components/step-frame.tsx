"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";

export interface StepProps {
  /** Go on to the next step (after saving, or without). */
  onNext: () => void;
}

/** A step: big headline, one line on why it matters, the controls, the primary action at the bottom. */
export function StepFrame({
  title,
  body,
  children,
  action,
  error,
}: {
  title: ReactNode;
  body: ReactNode;
  children?: ReactNode;
  /** The primary button(s), kept at the bottom for the thumb. */
  action?: ReactNode;
  error?: boolean;
}) {
  const t = useTranslations("onboarding");
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-black tracking-tight sm:text-4xl">{title}</h1>
        <p className="mt-2 text-base text-muted">{body}</p>
      </div>
      {children}
      {error ? (
        <p role="alert" className="rounded-control bg-bad-soft px-4 py-3 text-sm font-medium text-bad">
          {t("saveFailed")}
        </p>
      ) : null}
      {action ? <div className="flex flex-col gap-3">{action}</div> : null}
    </div>
  );
}

/** A "Save and continue" button that runs `save` and moves on when it worked. */
export function SaveButton({ busy, onClick }: { busy: boolean; onClick: () => void }) {
  const t = useTranslations("onboarding");
  const common = useTranslations("common.actions");
  return (
    <Button type="button" size="lg" block disabled={busy} onClick={onClick}>
      {busy ? common("saving") : t("saveAndContinue")}
    </Button>
  );
}

/** Runs one save at a time; `failed` until the next attempt. */
export function useSave(onNext: () => void) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const run = useCallback(
    async (save: () => Promise<boolean>) => {
      setBusy(true);
      setFailed(false);
      const ok = await save();
      setBusy(false);
      if (ok) onNext();
      else setFailed(true);
    },
    [onNext],
  );
  return { busy, failed, run };
}
