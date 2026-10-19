"use client";

import { Plus, Ticket, X } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmSheet } from "@/components/ui/confirm-sheet";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ResponsiveSheet } from "@/components/ui/sheet";
import { Empty } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { CopyLink } from "@/features/admin/components/copy-link";
import type { Invite, InviteCreated, InviteIn, InviteStatus } from "@/features/admin/types";
import { del, post } from "@/lib/mutate";

/** InviteIn's bound. */
export const NOTE_MAX_LENGTH = 200;

const STATUS_TONE: Record<InviteStatus, Tone> = { open: "accent", used: "ok", expired: "neutral", revoked: "bad" };

/** The invite as `InviteOut` (the list's shape), without the one-time code and link. */
function listed(created: InviteCreated): Invite {
  const { id, note, created_at, expires_at, used_at, revoked_at, status } = created;
  return { id, note, created_at, expires_at, used_at, revoked_at, status };
}

/**
 * Invites: create (`POST /v1/admin/invites`, an optional note; the link is shown once), the list
 * with status, revoke an open one (`DELETE /v1/admin/invites/{id}`).
 */
export function InvitesPanel({ initial }: { initial: Invite[] }) {
  const t = useTranslations("admin.invites");
  const common = useTranslations("common.actions");
  const toast = useToast();
  const [invites, setInvites] = useState(initial);
  const [note, setNote] = useState("");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<InviteCreated | null>(null);
  const [target, setTarget] = useState<Invite | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function create(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    const body: InviteIn = { note: note.trim() || null };
    const result = await post<InviteCreated>("/v1/admin/invites", body);
    setCreating(false);
    if (!result.ok || !result.data) return toast(t("createFailed"), "bad");
    const invite = result.data;
    setInvites((list) => [listed(invite), ...list]);
    setNote("");
    setCreated(invite);
  }

  async function revoke(invite: Invite) {
    setBusy(true);
    setFailed(false);
    const result = await del(`/v1/admin/invites/${invite.id}`);
    setBusy(false);
    if (!result.ok) return setFailed(true);
    const now = new Date().toISOString();
    setInvites((list) => list.map((i) => (i.id === invite.id ? { ...i, status: "revoked", revoked_at: now } : i)));
    setTarget(null);
    toast(t("revoked"), "ok");
  }

  return (
    <section aria-labelledby="admin-invites" className="flex flex-col gap-4 rounded-card border border-border bg-surface p-4 shadow-card sm:p-5">
      <div>
        <h2 id="admin-invites" className="text-lg font-bold tracking-tight">
          {t("title")}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("body")}</p>
      </div>
      <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={(event) => void create(event)}>
        <Field label={t("note")} hint={t("noteHint")} className="flex-1">
          <Input maxLength={NOTE_MAX_LENGTH} value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>
        <Button type="submit" size="lg" disabled={creating} className="sm:mb-6">
          <Plus aria-hidden />
          {t("create")}
        </Button>
      </form>
      {invites.length === 0 ? (
        <Empty title={t("empty")}>{t("emptyBody")}</Empty>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {invites.map((invite) => (
            <InviteRow key={invite.id} invite={invite} onRevoke={() => setTarget(invite)} />
          ))}
        </ul>
      )}
      <ResponsiveSheet
        open={created !== null}
        onOpenChange={(open) => {
          if (!open) setCreated(null);
        }}
        title={t("createdTitle")}
        description={t("createdBody")}
        closeLabel={common("close")}
      >
        {created ? (
          <div className="flex flex-col gap-4">
            <CopyLink label={t("link")} url={created.url} />
            <Button type="button" variant="secondary" size="lg" onClick={() => setCreated(null)}>
              {common("done")}
            </Button>
          </div>
        ) : null}
      </ResponsiveSheet>
      <ConfirmSheet
        open={target !== null}
        onOpenChange={(open) => {
          if (!open) setTarget(null);
          setFailed(false);
        }}
        title={t("revokeTitle")}
        description={t("revokeBody")}
        confirmLabel={t("revoke")}
        cancelLabel={common("cancel")}
        closeLabel={common("close")}
        busy={busy}
        error={failed ? t("revokeFailed") : undefined}
        onConfirm={() => {
          if (target) void revoke(target);
        }}
      />
    </section>
  );
}

function InviteRow({ invite, onRevoke }: { invite: Invite; onRevoke: () => void }) {
  const t = useTranslations("admin.invites");
  const format = useFormatter();
  const date = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "medium" });
  const label = invite.note || t("noNote");
  return (
    <li className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
      <span aria-hidden className="mt-0.5 grid size-10 shrink-0 place-items-center rounded-control bg-surface-2 text-muted">
        <Ticket className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2">
          <span className="truncate font-semibold">{label}</span>
          <Badge tone={STATUS_TONE[invite.status]}>{t(`status.${invite.status}`)}</Badge>
        </p>
        <p className="text-sm text-muted">{t("created", { date: date(invite.created_at) })}</p>
        <p className="text-sm text-muted">
          {invite.used_at
            ? t("usedOn", { date: date(invite.used_at) })
            : invite.revoked_at
              ? t("revokedOn", { date: date(invite.revoked_at) })
              : t("expires", { date: date(invite.expires_at) })}
        </p>
      </div>
      {invite.status === "open" ? (
        <Button type="button" variant="ghost" size="icon" aria-label={t("revokeLabel", { invite: label })} onClick={onRevoke}>
          <X aria-hidden />
        </Button>
      ) : null}
    </li>
  );
}
