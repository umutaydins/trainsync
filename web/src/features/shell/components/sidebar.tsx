"use client";

import { LogOut } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { cn } from "@/lib/cn";
import { LinkPending } from "@/features/shell/components/link-pending";
import { Logo } from "@/features/shell/components/logo";
import { isActive, visibleNav } from "@/features/shell/nav";
import type { Me } from "@/lib/types";

type Account = Pick<Me, "display_name" | "email">;

/** The name to greet: the display name, else the email's local part; never the role. */
export function shownName(account: Account | null): string {
  if (!account) return "";
  return account.display_name.trim() || account.email.split("@", 1)[0] || account.email;
}

/**
 * The desktop sidebar: every section, the owner's admin entry, sign out. The panel runs the full
 * page height; its content sticks to the viewport while the page scrolls.
 */
export function Sidebar({ isOwner, account }: { isOwner: boolean; account: Account | null }) {
  const pathname = usePathname();
  const t = useTranslations("nav");
  const common = useTranslations("common");
  return (
    <aside className="hidden w-60 shrink-0 border-r border-border bg-surface md:block" data-testid="sidebar">
      <div className="sticky top-0 flex h-dvh flex-col overflow-y-auto px-3 py-5">
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
          <p className="truncate px-3 text-sm font-medium" data-testid="sidebar-name">
            {shownName(account)}
          </p>
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
      </div>
    </aside>
  );
}
