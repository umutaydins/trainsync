import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Logo } from "@/features/shell/components/logo";
import { cn } from "@/lib/cn";

/**
 * The signed-out pages (sign-in, register, reset, legal): a bold brand panel with the accent
 * stripes (a header strip on phones; on desktop a half as tall as the page, its content sticky)
 * and the page beside it. The stripes have their own column at the right edge and the text keeps
 * clear of it at every width.
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
    <div className="min-h-dvh [--stripes-w:6rem] lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:[--stripes-w:8vw]">
      <header className="border-b border-border bg-surface lg:border-b-0 lg:border-r" data-testid="auth-hero">
        <div className="relative isolate overflow-hidden px-5 pb-7 pt-[max(1.25rem,env(safe-area-inset-top))] lg:sticky lg:top-0 lg:flex lg:h-dvh lg:flex-col lg:justify-between lg:p-12">
          <Stripes />
          <Link href="/login" className="inline-flex items-center gap-2.5 rounded-control">
            <Logo className="size-9" />
            <span className="text-lg font-bold tracking-tight">{common("appName")}</span>
          </Link>
          {/* Right padding = the stripes' column + a gap, so no word ever sits on a stripe. */}
          <div className="mt-6 pr-[calc(var(--stripes-w)+1rem)] lg:mt-0 lg:pr-[var(--stripes-w)]" data-testid="auth-hero-text">
            <p className="max-w-[16ch] text-3xl font-black uppercase italic leading-[0.95] tracking-tight sm:text-4xl lg:max-w-md lg:text-[clamp(2rem,3.4vw,3.5rem)]">
              {t("tagline")}
            </p>
            <p className="mt-5 hidden max-w-sm text-base text-muted lg:block">{t("pitch")}</p>
          </div>
          <div aria-hidden className="hidden h-1.5 w-24 rounded-full bg-accent lg:block" />
        </div>
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

/**
 * Two slanted accent bands at the panel's edge: speed, not decoration for its own sake. They are
 * clipped to their own column (`--stripes-w`, set on the panel), so they never reach the text.
 */
function Stripes() {
  return (
    <div aria-hidden data-testid="auth-stripes" className="pointer-events-none absolute inset-y-0 right-0 -z-10 w-[var(--stripes-w)] overflow-hidden">
      <div className="absolute inset-0 bg-accent [clip-path:polygon(40%_0,75%_0,35%_100%,0_100%)]" />
      <div className="absolute inset-0 bg-accent/40 [clip-path:polygon(85%_0,100%_0,60%_100%,45%_100%)]" />
    </div>
  );
}
