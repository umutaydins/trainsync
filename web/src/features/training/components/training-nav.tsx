"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export const TRAINING_LINKS = [
  { href: "/training", label: "Today" },
  { href: "/training/programs", label: "Programs" },
  { href: "/training/history", label: "History" },
  { href: "/training/progress", label: "Progress" },
] as const;

/** Section tabs under /training. Horizontally scrollable on narrow screens. */
export function TrainingNav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Training" className="-mx-4 mb-5 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <ul className="flex gap-1 border-b border-border">
        {TRAINING_LINKS.map(({ href, label }) => {
          const active = href === "/training" ? pathname === "/training" || pathname.startsWith("/training/workout") : pathname.startsWith(href);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={`-mb-px inline-flex min-h-11 items-center whitespace-nowrap border-b-2 px-3 text-sm font-medium ${
                  active ? "border-accent text-text" : "border-transparent text-muted hover:text-text"
                }`}
              >
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
