import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { PageTitle } from "@/components/ui/page-header";

/** A page of Me: back to the hub (thumb-friendly on phones), the title, the cards. */
export function SettingsPage({ title, subtitle, children }: { title: ReactNode; subtitle?: ReactNode; children: ReactNode }) {
  const nav = useTranslations("nav");
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
      <Link
        href="/me"
        className="-ml-2 inline-flex h-touch items-center gap-1.5 self-start rounded-control px-2 text-sm font-semibold text-muted hover:text-text"
      >
        <ArrowLeft aria-hidden className="size-4" />
        {nav("me")}
      </Link>
      <PageTitle title={title} subtitle={subtitle} />
      {children}
    </div>
  );
}

/** One group of settings on a page. */
export function SettingsCard({
  title,
  body,
  children,
  id,
}: {
  title: ReactNode;
  body?: ReactNode;
  children: ReactNode;
  id: string;
}) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4 rounded-card border border-border bg-surface p-4 shadow-card sm:p-5">
      <div>
        <h2 id={id} className="text-lg font-bold tracking-tight">
          {title}
        </h2>
        {body ? <p className="mt-1 text-sm text-muted">{body}</p> : null}
      </div>
      {children}
    </section>
  );
}
