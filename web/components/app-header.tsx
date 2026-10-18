import Link from "next/link";

import { NavLinks } from "@/components/nav-links";

export function AppHeader() {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface/85 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-2 px-4 sm:gap-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <svg aria-hidden="true" viewBox="0 0 32 32" className="size-6">
            <rect width="32" height="32" rx="8" className="fill-accent" />
            <path
              d="M7 21l6-8 5 5 7-9"
              fill="none"
              stroke="white"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="hidden sm:inline">trainsync</span>
        </Link>
        <NavLinks />
        <form method="post" action="/api/auth/logout" className="ml-auto">
          <button
            type="submit"
            className="whitespace-nowrap rounded-md px-2 py-1.5 text-sm text-muted transition hover:bg-surface-2 hover:text-text sm:px-2.5"
          >
            Sign out
          </button>
        </form>
      </div>
    </header>
  );
}
