import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Logo } from "@/features/shell/components/logo";
import { cn } from "@/lib/cn";

/**
 * The signed-out pages (sign-in, register, reset, legal): a bold brand panel with the accent
 * stripes (a header strip on phones, a sticky half on desktop) and the page beside it.
 */
export function AuthLayout({
  title,
  subtitle,
  wide = false,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  /** Reading pages (privacy, terms) get a wider column. */
  wide?: boolean;
  children: ReactNode;
}) {
  const t = useTranslations("auth.layout");
  const common = useTranslations("common");
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <header className="relative isolate overflow-hidden border-b border-border bg-surface px-5 pb-7 pt-[max(1.25rem,env(safe-area-inset-top))] lg:sticky lg:top-0 lg:flex lg:h-dvh lg:flex-col lg:justify-between lg:border-b-0 lg:border-r lg:p-12">
        <Stripes />
        <Link href="/login" className="inline-flex items-center gap-2.5 rounded-control">
          <Logo className="size-9" />
          <span className="text-lg font-bold tracking-tight">{common("appName")}</span>
        </Link>
        <div className="mt-6 max-w-[16ch] lg:mt-0 lg:max-w-md">
          <p className="text-3xl font-black uppercase italic leading-[0.95] tracking-tight sm:text-4xl lg:text-hero">
            {t("tagline")}
          </p>
          <p className="mt-5 hidden max-w-sm text-base text-muted lg:block">{t("pitch")}</p>
        </div>
        <div aria-hidden className="hidden h-1.5 w-24 rounded-full bg-accent lg:block" />
      </header>
      <div className="flex min-h-[calc(100dvh-12rem)] flex-col px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-8 sm:px-8 lg:min-h-dvh lg:px-16 lg:pt-16">
        <main className={cn("mx-auto w-full flex-1 lg:flex lg:flex-col lg:justify-center", wide ? "max-w-2xl" : "max-w-md")}>
          <h1 className="text-4xl font-black tracking-tight sm:text-5xl">{title}</h1>
          {subtitle ? <p className="mt-2 text-base text-muted">{subtitle}</p> : null}
          <div className="mt-8">{children}</div>
        </main>
        <footer className={cn("mx-auto mt-10 w-full", wide ? "max-w-2xl" : "max-w-md")}>
          <nav aria-label={t("legal")} className="flex flex-wrap gap-x-5 text-sm text-muted">
            <Link href="/privacy" className="inline-flex h-touch items-center underline-offset-4 hover:text-text hover:underline">
              {t("privacy")}
            </Link>
            <Link href="/terms" className="inline-flex h-touch items-center underline-offset-4 hover:text-text hover:underline">
              {t("terms")}
            </Link>
          </nav>
        </footer>
      </div>
    </div>
  );
}

/** Two slanted accent bands at the panel's edge: speed, not decoration for its own sake. */
function Stripes() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 -z-10 w-28 lg:w-56">
      <div className="absolute inset-y-[-20%] right-6 w-8 -skew-x-[18deg] bg-accent lg:right-16 lg:w-16" />
      <div className="absolute inset-y-[-20%] right-[-1rem] w-4 -skew-x-[18deg] bg-accent/40 lg:right-4 lg:w-8" />
    </div>
  );
}
