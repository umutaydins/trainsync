"use client";

import { CircleAlert, CircleCheck, CircleDashed, Unlink } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ConfirmSheet } from "@/components/ui/confirm-sheet";
import { useToast } from "@/components/ui/toast";
import { PoweredByStrava, StravaConnectButton } from "@/features/onboarding/components/strava-step";
import { TelegramCodeCard, TelegramStatus, useTelegramLink } from "@/features/onboarding/components/telegram-link";
import type { StravaReturn } from "@/features/onboarding/types";
import { SettingsCard } from "@/features/settings/components/settings-page";
import type { LinkStatus, StravaConnection } from "@/features/settings/types";
import { del } from "@/lib/mutate";

/** Strava sends the browser back here (allowlisted in the connect route and the API). */
export const STRAVA_CONNECT_FROM_SETTINGS = "/api/strava/connect?return_to=/me/connections";

/** Confirm, then DELETE; `onDone` after it worked. */
function useDisconnect(path: string, onDone: () => void, doneText: string) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  async function confirm() {
    setBusy(true);
    setFailed(false);
    const result = await del(path);
    setBusy(false);
    if (!result.ok) return setFailed(true);
    setOpen(false);
    onDone();
    toast(doneText, "ok");
  }
  const onOpenChange = (next: boolean) => {
    setOpen(next);
    setFailed(false);
  };
  return { open, onOpenChange, busy, failed, confirm };
}

/** Strava: status, the official connect button, disconnect (`DELETE /v1/me/strava`). */
export function StravaCard({ initial, returned }: { initial: StravaConnection; returned: StravaReturn }) {
  const t = useTranslations("settings.connections");
  const onboarding = useTranslations("onboarding.strava");
  const common = useTranslations("common.actions");
  const format = useFormatter();
  const [connection, setConnection] = useState(initial);
  const disconnect = useDisconnect("/v1/me/strava", () => setConnection({ connected: false }), t("disconnected"));
  const connected = connection.connected;
  const failure = returned && "error" in returned ? returned.error : null;

  return (
    <SettingsCard id="connections-strava" title={t("strava")} body={t("stravaBody")}>
      <div role="status" className="flex items-start gap-3 rounded-control bg-surface-2 p-4 text-sm">
        {connected ? (
          <CircleCheck aria-hidden className="mt-0.5 size-5 shrink-0 text-ok" />
        ) : failure ? (
          <CircleAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-bad" />
        ) : (
          <CircleDashed aria-hidden className="mt-0.5 size-5 shrink-0 text-muted" />
        )}
        <div>
          <p className="font-semibold">{connected ? onboarding("connected") : onboarding("notConnected")}</p>
          {connected && connection.connected_at ? (
            <p className="mt-0.5 text-muted">
              {t("connectedSince", { date: format.dateTime(new Date(connection.connected_at), { dateStyle: "medium" }) })}
            </p>
          ) : null}
          {!connected && failure ? <p className="mt-0.5 text-bad">{onboarding("failed", { reason: failure })}</p> : null}
        </div>
      </div>
      {connected ? (
        <Button type="button" variant="outline" className="self-start" onClick={() => disconnect.onOpenChange(true)}>
          <Unlink aria-hidden />
          {t("disconnect")}
        </Button>
      ) : (
        <StravaConnectButton href={STRAVA_CONNECT_FROM_SETTINGS} />
      )}
      <PoweredByStrava />
      <ConfirmSheet
        open={disconnect.open}
        onOpenChange={disconnect.onOpenChange}
        title={t("disconnectTitle")}
        description={t("disconnectBody")}
        confirmLabel={t("disconnect")}
        cancelLabel={common("cancel")}
        closeLabel={common("close")}
        busy={disconnect.busy}
        error={disconnect.failed ? t("failed") : undefined}
        onConfirm={() => void disconnect.confirm()}
      />
    </SettingsCard>
  );
}

/** Telegram: status, link with a one-time code, unlink (`DELETE /v1/me/telegram`). */
export function TelegramCard({ initial }: { initial: LinkStatus }) {
  const t = useTranslations("settings.connections");
  const onboarding = useTranslations("onboarding.telegram");
  const common = useTranslations("common.actions");
  const link = useTelegramLink(initial);
  const unlink = useDisconnect("/v1/me/telegram", link.reset, t("unlinked"));

  return (
    <SettingsCard id="connections-telegram" title={t("telegram")} body={t("telegramBody")}>
      <TelegramStatus status={link.status} />
      {link.failed ? (
        <p role="alert" className="rounded-control bg-bad-soft px-4 py-3 text-sm font-medium text-bad">
          {onboarding("codeFailed")}
        </p>
      ) : null}
      {link.code && !link.linked ? (
        <TelegramCodeCard code={link.code} busy={link.busy} onNewCode={() => void link.createCode()} />
      ) : null}
      {link.linked ? (
        <Button type="button" variant="outline" className="self-start" onClick={() => unlink.onOpenChange(true)}>
          <Unlink aria-hidden />
          {t("unlink")}
        </Button>
      ) : link.code ? (
        <Button type="button" variant="secondary" className="self-start" disabled={link.busy} onClick={() => void link.check()}>
          {onboarding("check")}
        </Button>
      ) : (
        <Button type="button" className="self-start" disabled={link.busy} onClick={() => void link.createCode()}>
          {onboarding("getCode")}
        </Button>
      )}
      <ConfirmSheet
        open={unlink.open}
        onOpenChange={unlink.onOpenChange}
        title={t("unlinkTitle")}
        description={t("unlinkBody")}
        confirmLabel={t("unlink")}
        cancelLabel={common("cancel")}
        closeLabel={common("close")}
        busy={unlink.busy}
        error={unlink.failed ? t("failed") : undefined}
        onConfirm={() => void unlink.confirm()}
      />
    </SettingsCard>
  );
}
