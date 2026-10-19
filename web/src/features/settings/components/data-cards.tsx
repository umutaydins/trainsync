"use client";

import { Download, Trash2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ConfirmSheet } from "@/components/ui/confirm-sheet";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { deleteAccount, leaveTo } from "@/features/settings/account";
import { SettingsCard } from "@/features/settings/components/settings-page";
import { confirmMatches } from "@/features/settings/settings-form";

/** The route handler that streams `GET /v1/me/export` as a file. */
export const EXPORT_HREF = "/api/account/export";

const UNAUTHORIZED = 401;
const FORBIDDEN = 403;

/** Me → Data → Export: every row of the account as one JSON file. */
export function ExportCard() {
  const t = useTranslations("settings.data");
  return (
    <SettingsCard id="data-export" title={t("export")} body={t("exportBody")}>
      <Button asChild size="lg" variant="secondary" className="self-start">
        <a href={EXPORT_HREF} download>
          <Download aria-hidden />
          {t("exportButton")}
        </a>
      </Button>
    </SettingsCard>
  );
}

type DeleteError = "wrongPassword" | "ownerCannot" | "deleteFailed";

/**
 * Me → Data → Delete account: the password (`DeleteAccountIn`) and the typed word, then
 * `DELETE /api/account`, which also ends the browser session; then the sign-in page.
 */
export function DeleteAccountCard({ isOwner }: { isOwner: boolean }) {
  const t = useTranslations("settings.data");
  const common = useTranslations("common.actions");
  const locale = useLocale();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<DeleteError | null>(null);
  const word = t("confirmWord");
  const ready = password.length > 0 && confirmMatches(typed, word, locale);

  async function confirm() {
    setBusy(true);
    setError(null);
    const result = await deleteAccount(password);
    if (result.ok) return leaveTo("/login");
    setBusy(false);
    setError(
      result.status === UNAUTHORIZED ? "wrongPassword" : result.status === FORBIDDEN ? "ownerCannot" : "deleteFailed",
    );
  }

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setPassword("");
      setTyped("");
      setError(null);
    }
  }

  return (
    <SettingsCard id="data-delete" title={t("delete")} body={t("deleteBody")}>
      {isOwner ? (
        <p className="rounded-control bg-surface-2 px-4 py-3 text-sm text-muted">{t("ownerCannot")}</p>
      ) : (
        <Button type="button" variant="danger" size="lg" className="self-start" onClick={() => setOpen(true)}>
          <Trash2 aria-hidden />
          {t("deleteButton")}
        </Button>
      )}
      <ConfirmSheet
        open={open}
        onOpenChange={onOpenChange}
        title={t("deleteTitle")}
        description={t("deleteWarning")}
        confirmLabel={busy ? t("deleting") : t("deleteButton")}
        cancelLabel={common("cancel")}
        closeLabel={common("close")}
        busy={busy}
        canConfirm={ready}
        error={error ? t(error) : undefined}
        onConfirm={() => void confirm()}
      >
        <Field label={t("password")}>
          <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Field label={t("confirmLabel", { word })}>
          <Input autoComplete="off" autoCapitalize="characters" spellCheck={false} value={typed} onChange={(e) => setTyped(e.target.value)} />
        </Field>
      </ConfirmSheet>
    </SettingsCard>
  );
}
