import { ArrowLeft, KeyRound, Link2, MailX } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { buttonVariants } from "@/components/ui/button";

const STEPS = [
  { key: "noEmail", icon: MailX },
  { key: "askOwner", icon: KeyRound },
  { key: "openLink", icon: Link2 },
] as const;

/** No email delivery yet (ADR 0034): the owner creates a one-time reset link for the account. */
export function ForgotPassword() {
  const t = useTranslations("auth.forgot");
  return (
    <div className="flex flex-col gap-6">
      <ol className="flex flex-col gap-3">
        {STEPS.map(({ key, icon: Icon }, index) => (
          <li key={key} className="flex gap-4 rounded-card border border-border bg-surface p-4">
            <span className="grid size-10 shrink-0 place-items-center rounded-full bg-accent-soft text-accent-ink">
              <Icon aria-hidden className="size-5" />
              <span className="sr-only">{index + 1}</span>
            </span>
            <p className="self-center text-sm">{t(key)}</p>
          </li>
        ))}
      </ol>
      <Link href="/login" className={buttonVariants({ variant: "secondary", size: "lg", block: true })}>
        <ArrowLeft aria-hidden />
        {t("back")}
      </Link>
    </div>
  );
}
