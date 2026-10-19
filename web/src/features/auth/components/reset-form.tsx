"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PASSWORD_MIN_LENGTH, resetError } from "@/features/auth/errors";

/** Where a changed password lands: sign-in with a success notice. */
export const RESET_DONE_PATH = "/login?reset=1";

/** New password + confirmation for an owner-generated reset link → `POST /api/auth/reset`. */
export function ResetForm({ token }: { token: string }) {
  const t = useTranslations("auth");
  const router = useRouter();
  const [mismatch, setMismatch] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    setError(null);
    if (password !== String(form.get("confirm") ?? "")) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    setPending(true);
    let status = 0;
    try {
      const response = await fetch("/api/auth/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      if (response.ok) {
        router.push(RESET_DONE_PATH);
        return;
      }
      status = response.status;
    } catch {
      status = 0;
    }
    setError(t(`reset.errors.${resetError(status)}`, { min: PASSWORD_MIN_LENGTH }));
    setPending(false);
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-5">
      <Field label={t("fields.newPassword")} hint={t("fields.passwordHint", { min: PASSWORD_MIN_LENGTH })}>
        <Input name="password" type="password" required minLength={PASSWORD_MIN_LENGTH} autoComplete="new-password" autoFocus />
      </Field>
      <Field label={t("fields.confirmPassword")} error={mismatch ? t("reset.errors.mismatch") : undefined}>
        <Input name="confirm" type="password" required minLength={PASSWORD_MIN_LENGTH} autoComplete="new-password" />
      </Field>
      {error ? (
        <p id="reset-error" role="alert" className="rounded-control bg-bad-soft px-4 py-3 text-sm font-medium text-bad">
          {error}
        </p>
      ) : null}
      <Button type="submit" size="lg" block disabled={pending}>
        {pending ? t("reset.submitting") : t("reset.submit")}
      </Button>
    </form>
  );
}
