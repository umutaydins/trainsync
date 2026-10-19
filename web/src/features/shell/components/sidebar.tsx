"use client";

import { LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { cn } from "@/lib/cn";
import { LinkPending } from "@/features/shell/components/link-pending";
import { Logo } from "@/features/shell/components/logo";
import { isActive, visibleNav } from "@/features/shell/nav";

/** The desktop sidebar: every section, the owner's admin entry, sign out. */
export function Sidebar({ isOwner, name }: { isOwner: boolean; name: string }) {
  const pathname = usePathname();
  const t = useTranslations("nav");
  const common = useTranslations("common");
  return (
    <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-border bg-surface px-3 py-5 md:flex">
      <Link href="/" aria-label={t("home")} className="mb-6 flex items-center gap-2.5 px-3">
        <Logo />
        <span className="text-lg font-bold tracking-tight">{common("appName")}</span>
      </Link>
      <nav aria-label={t("main")} className="flex-1">
        <ul className="flex flex-col gap-1">
          {visibleNav(isOwner).map(({ key, href, icon: Icon }) => {
            const active = isActive(href, pathname);
            return (
              <li key={key}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "relative flex h-touch items-center gap-3 rounded-control px-3 text-sm font-semibold transition",
                    active ? "bg-accent text-accent-contrast" : "text-muted hover:bg-surface-2 hover:text-text",
                  )}
                >
                  <Icon aria-hidden className="size-5" />
                  {t(key)}
                  <LinkPending />
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="border-t border-border pt-4">
        <p className="truncate px-3 text-sm font-medium">{name}</p>
        <form method="post" action="/api/auth/logout" className="mt-2">
          <button
            type="submit"
            className="flex h-touch w-full items-center gap-3 rounded-control px-3 text-sm font-semibold text-muted transition hover:bg-surface-2 hover:text-text"
          >
            <LogOut aria-hidden className="size-5" />
            {common("actions.signOut")}
          </button>
        </form>
      </div>
    </aside>
  );
}
