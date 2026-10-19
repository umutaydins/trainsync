"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { cn } from "@/lib/cn";
import { NAV, isActive } from "@/features/shell/nav";

/** The phone's bottom tab bar: thumb-reachable, above the home indicator (safe area). */
export function TabBar() {
  const pathname = usePathname();
  const t = useTranslations("nav");
  return (
    <nav
      aria-label={t("main")}
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-surface/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden"
    >
      <ul className="mx-auto grid h-tabbar max-w-lg grid-cols-5">
        {NAV.filter((item) => item.tab).map(({ key, href, icon: Icon }) => {
          const active = isActive(href, pathname);
          return (
            <li key={key}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-full flex-col items-center justify-center gap-1 text-[0.7rem] font-semibold transition",
                  active ? "text-accent-ink" : "text-muted",
                )}
              >
                <span
                  className={cn(
                    "grid h-8 w-14 place-items-center rounded-full transition",
                    active && "bg-accent-soft",
                  )}
                >
                  <Icon aria-hidden className="size-5" strokeWidth={active ? 2.5 : 2} />
                </span>
                {t(key)}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
