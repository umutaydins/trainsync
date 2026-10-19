import type { Metadata } from "next";

import { LoginForm } from "@/features/auth/components/login-form";
import { safeNextPath } from "@/lib/session";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { next } = await searchParams;
  return (
    <main className="flex min-h-dvh items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-2xl border border-border bg-surface p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-2">
          <Logo />
          <span className="text-lg font-semibold tracking-tight">trainsync</span>
        </div>
        <h1 className="text-xl font-semibold tracking-tight">Sign in</h1>
        <p className="mt-1 text-sm text-muted">Sign in with your trainsync account.</p>
        <LoginForm next={safeNextPath(typeof next === "string" ? next : undefined)} />
      </div>
    </main>
  );
}

function Logo() {
  return (
    <svg aria-hidden="true" viewBox="0 0 32 32" className="size-7">
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
  );
}
