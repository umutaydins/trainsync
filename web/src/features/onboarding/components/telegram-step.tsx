"use client";

import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { StepFrame, type StepProps } from "@/features/onboarding/components/step-frame";
import { TelegramCodeCard, TelegramStatus, useTelegramLink } from "@/features/onboarding/components/telegram-link";
import type { LinkStatus } from "@/features/onboarding/types";

/** Link the Telegram bot with a one-time code. */
export function TelegramStep({ onNext, initial }: StepProps & { initial: LinkStatus | null }) {
  const t = useTranslations("onboarding");
  const link = useTelegramLink(initial);

  return (
    <StepFrame
      title={t("telegram.title")}
      body={t("telegram.body")}
      action={
        link.linked ? (
          <Button type="button" size="lg" block onClick={onNext}>
            {t("continue")}
          </Button>
        ) : link.code ? (
          <Button type="button" size="lg" variant="secondary" block disabled={link.busy} onClick={() => void link.check()}>
            {t("telegram.check")}
          </Button>
        ) : (
          <Button type="button" size="lg" block disabled={link.busy} onClick={() => void link.createCode()}>
            {t("telegram.getCode")}
          </Button>
        )
      }
    >
      <TelegramStatus status={link.status} />
      {link.failed ? (
        <p role="alert" className="rounded-control bg-bad-soft px-4 py-3 text-sm font-medium text-bad">
          {t("telegram.codeFailed")}
        </p>
      ) : null}
      {link.code && !link.linked ? (
        <TelegramCodeCard code={link.code} busy={link.busy} onNewCode={() => void link.createCode()} />
      ) : null}
    </StepFrame>
  );
}
