"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { loginError } from "@/features/auth/errors";

/** Posts to /api/auth/login; on success the handler redirects (303) and sets the session cookie. */
export function LoginForm({ next }: { next: string }) {
  const t = useTranslations("auth");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    let status = 0;
    let retryAfter: string | null = null;
    try {
      const response = await fetch("/api/auth/login", { method: "POST", body: form });
      if (response.ok && response.redirected) {
        window.location.assign(response.url);
        return;
      }
      status = response.status;
      retryAfter = response.headers.get("retry-after");
    } catch {
      status = 0;
    }
    const { key, minutes } = loginError(status, retryAfter);
    setError(t(`login.errors.${key}`, { minutes: minutes ?? 0 }));
    setPending(false);
  }

  return (
    <form method="post" action="/api/auth/login" onSubmit={onSubmit} className="flex flex-col gap-5">
      <input type="hidden" name="next" value={next} />
      <Field label={t("fields.email")}>
        <Input name="email" type="email" required autoComplete="username" autoFocus />
      </Field>
      <Field label={t("fields.password")}>
        <Input name="password" type="password" required autoComplete="current-password" />
      </Field>
      <div className="-mt-2 flex justify-end">
        <Link
          href="/forgot-password"
          className="inline-flex h-touch items-center text-sm font-semibold text-accent-ink underline-offset-4 hover:underline"
        >
          {t("login.forgot")}
        </Link>
      </div>
      {error ? (
        <p id="login-error" role="alert" className="rounded-control bg-bad-soft px-4 py-3 text-sm font-medium text-bad">
          {error}
        </p>
      ) : null}
      <Button type="submit" size="lg" block disabled={pending}>
        {pending ? t("login.submitting") : t("login.submit")}
        {pending ? null : <ArrowRight aria-hidden />}
      </Button>
      <p className="text-center text-sm text-muted">
        {t("login.noAccount")}{" "}
        <Link
          href="/register"
          className="inline-flex h-touch items-center font-semibold text-accent-ink underline-offset-4 hover:underline"
        >
          {t("login.register")}
        </Link>
      </p>
    </form>
  );
}
