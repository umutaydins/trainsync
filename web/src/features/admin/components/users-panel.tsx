"use client";

import { KeyRound } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ResponsiveSheet } from "@/components/ui/sheet";
import { Empty } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";
import { CopyLink } from "@/features/admin/components/copy-link";
import type { AdminUser, ResetLink } from "@/features/admin/types";
import { post } from "@/lib/mutate";

/**
 * Accounts (account facts only, never their data) and a one-time password reset link per account
 * (`POST /v1/admin/users/{id}/reset-link`), shown once.
 */
export function UsersPanel({ users }: { users: AdminUser[] }) {
  const t = useTranslations("admin.users");
  const common = useTranslations("common.actions");
  const format = useFormatter();
  const toast = useToast();
  const [busyId, setBusyId] = useState<number | null>(null);
  const [link, setLink] = useState<{ user: AdminUser; reset: ResetLink } | null>(null);

  async function resetLink(user: AdminUser) {
    setBusyId(user.id);
    const result = await post<ResetLink>(`/v1/admin/users/${user.id}/reset-link`);
    setBusyId(null);
    if (!result.ok || !result.data) return toast(t("resetFailed"), "bad");
    setLink({ user, reset: result.data });
  }

  return (
    <section aria-labelledby="admin-users" className="flex flex-col gap-4 rounded-card border border-border bg-surface p-4 shadow-card sm:p-5">
      <div>
        <h2 id="admin-users" className="text-lg font-bold tracking-tight">
          {t("title")}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("body")}</p>
      </div>
      {users.length === 0 ? (
        <Empty title={t("empty")} />
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {users.map((user) => (
            <li key={user.id} className="flex flex-wrap items-center gap-3 py-3 first:pt-0 last:pb-0">
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="truncate font-semibold">{user.display_name}</span>
                  {user.role === "owner" ? <Badge tone="accent">{t("owner")}</Badge> : null}
                </p>
                <p className="truncate text-sm text-muted">{user.email}</p>
                <p className="text-sm text-muted">
                  {t("joined", { date: format.dateTime(new Date(user.created_at), { dateStyle: "medium" }) })}
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                disabled={busyId === user.id}
                aria-label={t("resetLabel", { name: user.display_name })}
                onClick={() => void resetLink(user)}
              >
                <KeyRound aria-hidden />
                {t("reset")}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <ResponsiveSheet
        open={link !== null}
        onOpenChange={(open) => {
          if (!open) setLink(null);
        }}
        title={t("linkTitle", { name: link?.user.display_name ?? "" })}
        description={
          link
            ? t("linkBody", { time: format.dateTime(new Date(link.reset.expires_at), { dateStyle: "medium", timeStyle: "short" }) })
            : undefined
        }
        closeLabel={common("close")}
      >
        {link ? (
          <div className="flex flex-col gap-4">
            <CopyLink label={t("link")} url={link.reset.url} />
            <Button type="button" variant="secondary" size="lg" onClick={() => setLink(null)}>
              {common("done")}
            </Button>
          </div>
        ) : null}
      </ResponsiveSheet>
    </section>
  );
}
