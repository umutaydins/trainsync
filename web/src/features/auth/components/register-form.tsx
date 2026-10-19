"use client";

import { ArrowRight, Lock } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { Failure } from "@/components/ui/states";
import {
  PASSWORD_MIN_LENGTH,
  type RegisterErrors,
  type RegisterField,
  registerErrors,
} from "@/features/auth/errors";
import type { RegisterIn, RegistrationMode } from "@/features/auth/types";
import { useBrowserTimeZones } from "@/lib/time-zones";

const NO_ERRORS: RegisterErrors = { form: null, fields: {} };
const AFTER_SIGN_UP = "/onboarding";
const DISPLAY_NAME_MAX = 100;
const INVITE_CODE_MAX = 100;

/** The register page body for each registration mode (`null`: the mode could not be read). */
export function Registration({ mode, inviteCode = "" }: { mode: RegistrationMode | null; inviteCode?: string }) {
  const t = useTranslations("auth.register");
  if (mode === null) return <Failure title={t("errors.failed")} message={t("modeUnknown")} />;
  if (mode === "closed") {
    return (
      <div className="flex flex-col gap-6">
        <div role="status" className="flex gap-3 rounded-card border border-border bg-surface p-5">
          <Lock aria-hidden className="mt-0.5 size-5 shrink-0 text-muted" />
          <div>
            <p className="font-semibold">{t("closedTitle")}</p>
            <p className="mt-1 text-sm text-muted">{t("closedBody")}</p>
          </div>
        </div>
        <SignInLink />
      </div>
    );
  }
  return <RegisterForm withInvite={mode === "invite"} inviteCode={inviteCode} />;
}

/** Posts to /api/auth/register, which creates the account and signs it in (303 to onboarding). */
export function RegisterForm({ withInvite, inviteCode = "" }: { withInvite: boolean; inviteCode?: string }) {
  const t = useTranslations("auth");
  const { zone: browserZone, zones } = useBrowserTimeZones();
  const [zone, setZone] = useState("");
  const [errors, setErrors] = useState<RegisterErrors>(NO_ERRORS);
  const [pending, setPending] = useState(false);
  const shown: readonly RegisterField[] = withInvite
    ? ["email", "password", "display_name", "invite_code", "timezone"]
    : ["email", "password", "display_name", "timezone"];

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setErrors(NO_ERRORS);
    const form = new FormData(event.currentTarget);
    const text = (name: RegisterField) => String(form.get(name) ?? "").trim();
    const body: RegisterIn & { next: string } = {
      email: text("email"),
      password: String(form.get("password") ?? ""),
      display_name: text("display_name") || null,
      invite_code: withInvite ? text("invite_code") : null,
      timezone: zone || browserZone || null,
      next: AFTER_SIGN_UP,
    };
    try {
      const response = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      });
      if (response.ok && response.redirected) {
        window.location.assign(response.url);
        return;
      }
      const data: unknown = await response.json().catch(() => null);
      const detail = data && typeof data === "object" ? (data as { detail?: unknown }).detail : undefined;
      setErrors(placed(registerErrors(response.status, detail), shown));
    } catch {
      setErrors(registerErrors(0));
    }
    setPending(false);
  }

  const fieldError = (name: RegisterField) => {
    const key = errors.fields[name];
    return key ? t(`register.errors.${key}`, { min: PASSWORD_MIN_LENGTH }) : undefined;
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-5">
      <Field label={t("fields.email")} error={fieldError("email")}>
        <Input name="email" type="email" required autoComplete="email" autoFocus={!inviteCode} />
      </Field>
      <Field
        label={t("fields.password")}
        hint={t("fields.passwordHint", { min: PASSWORD_MIN_LENGTH })}
        error={fieldError("password")}
      >
        <Input name="password" type="password" required minLength={PASSWORD_MIN_LENGTH} autoComplete="new-password" />
      </Field>
      <Field label={t("fields.displayName")} hint={t("fields.displayNameHint")} error={fieldError("display_name")}>
        <Input name="display_name" autoComplete="nickname" maxLength={DISPLAY_NAME_MAX} />
      </Field>
      {withInvite ? (
        <Field label={t("fields.inviteCode")} hint={t("fields.inviteCodeHint")} error={fieldError("invite_code")}>
          <Input
            name="invite_code"
            required
            defaultValue={inviteCode}
            maxLength={INVITE_CODE_MAX}
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            className="font-mono"
          />
        </Field>
      ) : null}
      <Field label={t("fields.timezone")} hint={t("fields.timezoneHint")} error={fieldError("timezone")}>
        <Select name="timezone" value={zone || browserZone} onChange={(event) => setZone(event.target.value)}>
          {zones.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </Select>
      </Field>
      {errors.form ? (
        <p id="register-error" role="alert" className="rounded-control bg-bad-soft px-4 py-3 text-sm font-medium text-bad">
          {t(`register.errors.${errors.form}`, { min: PASSWORD_MIN_LENGTH })}
        </p>
      ) : null}
      <Button type="submit" size="lg" block disabled={pending}>
        {pending ? t("register.submitting") : t("register.submit")}
        {pending ? null : <ArrowRight aria-hidden />}
      </Button>
      <SignInLink />
    </form>
  );
}

/** A field error the form does not show (the invite code in `open` mode) becomes the form's. */
function placed(errors: RegisterErrors, shown: readonly RegisterField[]): RegisterErrors {
  const fields: RegisterErrors["fields"] = {};
  let form = errors.form;
  for (const [name, key] of Object.entries(errors.fields) as [RegisterField, RegisterErrors["form"]][]) {
    if (!key) continue;
    if (shown.includes(name)) fields[name] = key;
    else form ??= key;
  }
  return { form, fields };
}

function SignInLink() {
  const t = useTranslations("auth.register");
  return (
    <p className="text-center text-sm text-muted">
      {t("haveAccount")}{" "}
      <Link
        href="/login"
        className="inline-flex h-touch items-center font-semibold text-accent-ink underline-offset-4 hover:underline"
      >
        {t("signIn")}
      </Link>
    </p>
  );
}
