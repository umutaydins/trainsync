import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { PageTitle } from "@/components/ui/page-header";
import { Failure } from "@/components/ui/states";
import { SignOutButton } from "@/features/auth/components/sign-out-button";
import { visibleSections } from "@/features/settings/sections";
import type { Me } from "@/features/settings/types";

/**
 * `/me`: who is signed in, then one row per settings page (a list on phones, two columns on
 * desktop), set up again, the legal pages and sign out.
 */
export function SettingsHub({ me }: { me: Me | null }) {
  const t = useTranslations("settings");
  const nav = useTranslations("nav");
  const isOwner = me?.role === "owner";
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <PageTitle title={nav("me")} />
      {me ? <AccountHeader me={me} /> : <Failure title={t("loadFailed")} />}
      <nav aria-label={nav("me")}>
        <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {visibleSections(isOwner).map(({ key, href, icon: Icon }) => (
            <li key={key}>
              <Link
                href={href}
                className="flex min-h-18 items-center gap-4 rounded-card border border-border bg-surface px-4 py-3 shadow-card transition hover:border-muted focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
              >
                <span aria-hidden className="grid size-11 shrink-0 place-items-center rounded-control bg-surface-2 text-accent-ink">
                  <Icon className="size-5" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block font-bold">{t(`sections.${key}.title`)}</span>
                  <span className="block truncate text-sm text-muted">{t(`sections.${key}.hint`)}</span>
                </span>
                <ChevronRight aria-hidden className="size-5 shrink-0 text-muted" />
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="flex flex-col gap-4 border-t border-border pt-6">
        <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm font-semibold">
          <li>
            <Link href="/onboarding" className="inline-flex h-touch items-center text-accent-ink hover:underline">
              {t("links.setupAgain")}
            </Link>
          </li>
          <li>
            <Link href="/privacy" className="inline-flex h-touch items-center text-muted hover:text-text">
              {t("links.privacy")}
            </Link>
          </li>
          <li>
            <Link href="/terms" className="inline-flex h-touch items-center text-muted hover:text-text">
              {t("links.terms")}
            </Link>
          </li>
        </ul>
        <SignOutButton size="lg" block />
      </div>
    </div>
  );
}

function AccountHeader({ me }: { me: Me }) {
  const t = useTranslations("settings");
  const initial = me.display_name.trim().charAt(0).toLocaleUpperCase() || "?";
  return (
    <section aria-label={t("account")} className="flex items-center gap-4 rounded-card border border-border bg-surface p-5 shadow-card">
      <span aria-hidden className="grid size-16 shrink-0 place-items-center rounded-full bg-accent text-3xl font-black text-accent-contrast">
        {initial}
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2">
          <span className="truncate text-2xl font-black tracking-tight">{me.display_name}</span>
          {me.role === "owner" ? <Badge tone="accent">{t("owner")}</Badge> : null}
        </p>
        <p className="truncate text-sm text-muted">{me.email}</p>
        <p className="mt-1 text-xs font-semibold uppercase tracking-[0.08em] text-muted">{me.timezone}</p>
      </div>
    </section>
  );
}
