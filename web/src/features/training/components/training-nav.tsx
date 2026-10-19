"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";

export const TRAINING_LINKS = [
  { href: "/training", key: "start" },
  { href: "/training/programs", key: "programs" },
  { href: "/training/history", key: "history" },
  { href: "/training/checkins", key: "checkins" },
  { href: "/training/progress", key: "progress" },
] as const;

const WORKOUT_PATH = "/training/workout";

/**
 * Section tabs under /training, horizontally scrollable on phones. Hidden on the workout screen,
 * which is all about the next set.
 */
export function TrainingNav() {
  const t = useTranslations("training.nav");
  const pathname = usePathname();
  if (pathname.startsWith(WORKOUT_PATH)) return null;
  return (
    <nav aria-label={t("label")} className="-mx-4 mb-5 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <ul className="flex w-max gap-1 rounded-full border border-border bg-surface p-1">
        {TRAINING_LINKS.map(({ href, key }) => {
          const active = href === "/training" ? pathname === href : pathname.startsWith(href);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "inline-flex h-9 items-center whitespace-nowrap rounded-full px-4 text-sm font-semibold transition",
                  active ? "bg-accent text-accent-contrast" : "text-muted hover:text-text",
                )}
              >
                {t(key)}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
