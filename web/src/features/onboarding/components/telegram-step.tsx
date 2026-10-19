"use client";

import { CircleCheck, CircleDashed, Copy, Send } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { StepFrame, type StepProps } from "@/features/onboarding/components/step-frame";
import type { LinkCode, LinkStatus } from "@/features/onboarding/types";
import { bffGet } from "@/lib/bff-get";
import { post } from "@/lib/mutate";

/** Link the Telegram bot: a one-time code (`POST /v1/me/telegram/code`), status from `GET /v1/me/telegram`. */
export function TelegramStep({ onNext, initial }: StepProps & { initial: LinkStatus | null }) {
  const t = useTranslations("onboarding");
  const common = useTranslations("common.actions");
  const format = useFormatter();
  const toast = useToast();
  const [status, setStatus] = useState<LinkStatus | null>(initial);
  const [code, setCode] = useState<LinkCode | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const linked = status?.linked === true;

  async function createCode() {
    setBusy(true);
    setFailed(false);
    const result = await post<LinkCode>("/v1/me/telegram/code");
    setBusy(false);
    if (result.ok && result.data) setCode(result.data);
    else setFailed(true);
  }

  async function check() {
    setBusy(true);
    const result = await bffGet<LinkStatus>("/v1/me/telegram");
    setBusy(false);
    if (result.ok && result.data) setStatus(result.data);
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast(common("copied"), "ok");
    } catch {
      toast(t("telegram.copyFailed"), "bad");
    }
  }

  return (
    <StepFrame
      title={t("telegram.title")}
      body={t("telegram.body")}
      action={
        linked ? (
          <Button type="button" size="lg" block onClick={onNext}>
            {t("continue")}
          </Button>
        ) : code ? (
          <Button type="button" size="lg" variant="secondary" block disabled={busy} onClick={() => void check()}>
            {t("telegram.check")}
          </Button>
        ) : (
          <Button type="button" size="lg" block disabled={busy} onClick={() => void createCode()}>
            {t("telegram.getCode")}
          </Button>
        )
      }
    >
      <div role="status" className="flex items-start gap-3 rounded-card border border-border bg-surface p-4 text-sm">
        {linked ? (
          <CircleCheck aria-hidden className="mt-0.5 size-5 shrink-0 text-ok" />
        ) : (
          <CircleDashed aria-hidden className="mt-0.5 size-5 shrink-0 text-muted" />
        )}
        <div>
          <p className="font-semibold">{linked ? t("telegram.linked") : t("telegram.notLinked")}</p>
          {linked && status?.linked_at ? (
            <p className="mt-0.5 text-muted">
              {t("telegram.linkedSince", { date: format.dateTime(new Date(status.linked_at), { dateStyle: "medium" }) })}
            </p>
          ) : null}
        </div>
      </div>
      {failed ? (
        <p role="alert" className="rounded-control bg-bad-soft px-4 py-3 text-sm font-medium text-bad">
          {t("telegram.codeFailed")}
        </p>
      ) : null}
      {code && !linked ? (
        <section aria-labelledby="telegram-code" className="flex flex-col gap-4 rounded-card border-2 border-accent bg-surface p-5">
          <h2 id="telegram-code" className="text-label font-semibold uppercase tracking-[0.08em] text-muted">
            {t("telegram.codeLabel")}
          </h2>
          <div className="flex items-center justify-between gap-3">
            <output className="font-mono text-stat font-bold tracking-[0.2em] tabular sm:text-hero">{code.code}</output>
            <Button type="button" variant="secondary" size="icon" aria-label={common("copy")} onClick={() => void copy(code.code)}>
              <Copy aria-hidden />
            </Button>
          </div>
          <p className="text-sm text-muted">
            {t("telegram.expires", { time: format.dateTime(new Date(code.expires_at), { timeStyle: "short" }) })}
          </p>
          {code.bot_url ? (
            <Button asChild size="lg" block>
              <a href={code.bot_url} target="_blank" rel="noreferrer">
                <Send aria-hidden />
                {t("telegram.openBot")}
              </a>
            </Button>
          ) : null}
          <p className="text-sm">
            {t("telegram.sendCommand")} <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono">{code.command}</code>
          </p>
          <Button type="button" variant="ghost" size="sm" className="self-start" disabled={busy} onClick={() => void createCode()}>
            {t("telegram.newCode")}
          </Button>
        </section>
      ) : null}
    </StepFrame>
  );
}
