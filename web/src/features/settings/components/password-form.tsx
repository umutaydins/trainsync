"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { PASSWORD_MIN_LENGTH } from "@/features/auth/errors";
import { SettingsCard } from "@/features/settings/components/settings-page";
import type { PasswordChange } from "@/features/settings/types";
import { post } from "@/lib/mutate";

type ErrorKey = "required" | "wrongCurrent" | "tooShort" | "mismatch" | "failed";
type Errors = Partial<Record<"current" | "next" | "repeat" | "form", ErrorKey>>;

const UNAUTHORIZED = 401;
const UNPROCESSABLE = 422;

/** What is wrong with the form before it is sent, if anything. */
export function passwordErrors(current: string, next: string, repeat: string): Errors {
  if (!current) return { current: "required" };
  if (next.length < PASSWORD_MIN_LENGTH) return { next: "tooShort" };
  if (next !== repeat) return { repeat: "mismatch" };
  return {};
}

/** Me → Security: `POST /v1/me/password`; every other session of the account ends. */
export function PasswordForm() {
  const t = useTranslations("settings.security");
  const router = useRouter();
  const toast = useToast();
  const [values, setValues] = useState({ current: "", next: "", repeat: "" });
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const message = (key: ErrorKey | undefined) => (key ? t(key, { min: PASSWORD_MIN_LENGTH }) : undefined);
  const set = (key: keyof typeof values) => (event: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [key]: event.target.value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found = passwordErrors(values.current, values.next, values.repeat);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    const body: PasswordChange = { current_password: values.current, new_password: values.next };
    const result = await post("/v1/me/password", body);
    setBusy(false);
    if (result.ok) {
      setValues({ current: "", next: "", repeat: "" });
      toast(t("changed"), "ok");
      // The other sessions are gone: the list below re-reads.
      return router.refresh();
    }
    if (result.status === UNAUTHORIZED) return setErrors({ current: "wrongCurrent" });
    if (result.status === UNPROCESSABLE) return setErrors({ next: "tooShort" });
    setErrors({ form: "failed" });
  }

  return (
    <SettingsCard id="security-password" title={t("password")} body={t("passwordBody")}>
      <form className="flex flex-col gap-4" onSubmit={(event) => void submit(event)} noValidate>
        <Field label={t("current")} error={message(errors.current)}>
          <Input type="password" autoComplete="current-password" value={values.current} onChange={set("current")} />
        </Field>
        <Field label={t("new")} hint={t("newHint", { min: PASSWORD_MIN_LENGTH })} error={message(errors.next)}>
          <Input type="password" autoComplete="new-password" value={values.next} onChange={set("next")} />
        </Field>
        <Field label={t("repeat")} error={message(errors.repeat)}>
          <Input type="password" autoComplete="new-password" value={values.repeat} onChange={set("repeat")} />
        </Field>
        {errors.form ? (
          <p role="alert" className="rounded-control bg-bad-soft px-4 py-3 text-sm font-medium text-bad">
            {message(errors.form)}
          </p>
        ) : null}
        <Button type="submit" size="lg" className="sm:self-start" disabled={busy}>
          {t("submit")}
        </Button>
      </form>
    </SettingsCard>
  );
}
