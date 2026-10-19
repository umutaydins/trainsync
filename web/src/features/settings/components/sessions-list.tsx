"use client";

import { LogOut, Monitor, Smartphone } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmSheet } from "@/components/ui/confirm-sheet";
import { Empty } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { leaveTo, signOut } from "@/features/settings/account";
import { SettingsCard } from "@/features/settings/components/settings-page";
import { deviceName } from "@/features/settings/devices";
import type { Session } from "@/features/settings/types";
import { del } from "@/lib/mutate";

const PHONE = /iPhone|Android|Mobile/;

/**
 * Me → Security: every signed-in session with its device, first and last activity; sign one out
 * (`DELETE /v1/me/sessions/{id}`). Signing out this device ends the browser session as well.
 */
export function SessionsList({ initial }: { initial: Session[] }) {
  const t = useTranslations("settings.security");
  const common = useTranslations("common.actions");
  const toast = useToast();
  const [sessions, setSessions] = useState(initial);
  const [target, setTarget] = useState<Session | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function revoke(session: Session) {
    setBusy(true);
    setFailed(false);
    const result = await del(`/v1/me/sessions/${session.id}`);
    if (!result.ok) {
      setBusy(false);
      return setFailed(true);
    }
    if (session.current) {
      await signOut();
      return leaveTo("/login");
    }
    setBusy(false);
    setTarget(null);
    setSessions((list) => list.filter((s) => s.id !== session.id));
    toast(t("revoked"), "ok");
  }

  return (
    <SettingsCard id="security-sessions" title={t("sessions")} body={t("sessionsBody")}>
      {sessions.length === 0 ? (
        <Empty title={t("empty")} />
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {sessions.map((session) => (
            <SessionRow key={session.id} session={session} onRevoke={() => setTarget(session)} />
          ))}
        </ul>
      )}
      <ConfirmSheet
        open={target !== null}
        onOpenChange={(open) => {
          if (!open) setTarget(null);
          setFailed(false);
        }}
        title={target?.current ? t("revokeCurrentTitle") : t("revokeTitle")}
        description={target?.current ? t("revokeCurrentBody") : t("revokeBody")}
        confirmLabel={t("revoke")}
        cancelLabel={common("cancel")}
        closeLabel={common("close")}
        busy={busy}
        error={failed ? t("revokeFailed") : undefined}
        onConfirm={() => {
          if (target) void revoke(target);
        }}
      />
    </SettingsCard>
  );
}

function SessionRow({ session, onRevoke }: { session: Session; onRevoke: () => void }) {
  const t = useTranslations("settings.security");
  const format = useFormatter();
  const name = deviceName(session.user_agent) ?? t("unknownDevice");
  const Icon = session.user_agent && PHONE.test(session.user_agent) ? Smartphone : Monitor;
  const when = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "medium", timeStyle: "short" });
  return (
    <li className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
      <span aria-hidden className="mt-0.5 grid size-10 shrink-0 place-items-center rounded-control bg-surface-2 text-muted">
        <Icon className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 font-semibold">
          {name}
          {session.current ? <Badge tone="accent">{t("thisDevice")}</Badge> : null}
        </p>
        {session.user_agent ? <p className="truncate text-xs text-muted">{session.user_agent}</p> : null}
        <p className="mt-1 text-sm text-muted">{t("lastSeen", { date: when(session.last_seen_at) })}</p>
        <p className="text-sm text-muted">{t("created", { date: when(session.created_at) })}</p>
      </div>
      <Button type="button" variant="ghost" size="icon" aria-label={t("revokeLabel", { device: name })} onClick={onRevoke}>
        <LogOut aria-hidden />
      </Button>
    </li>
  );
}
