"use client";

import { useState, type FormEvent } from "react";

/** Posts to /api/auth/login; on success the handler redirects (303) and sets the session cookie. */
export function LoginForm({ next }: { next: string }) {
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch("/api/auth/login", { method: "POST", body: form });
      if (response.ok && response.redirected) {
        window.location.assign(response.url);
        return;
      }
      setError(errorMessage(response));
    } catch {
      setError("Network error. Try again.");
    }
    setPending(false);
  }

  return (
    <form method="post" action="/api/auth/login" onSubmit={onSubmit} className="mt-6 space-y-4">
      <input type="hidden" name="next" value={next} />
      <div className="space-y-1.5">
        <label htmlFor="password" className="block text-sm font-medium">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          required
          autoComplete="current-password"
          autoFocus
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "login-error" : undefined}
          className="block w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/30"
        />
      </div>
      {error ? (
        <p id="login-error" role="alert" className="text-sm text-bad">
          {error}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={pending}
        className="w-full rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-accent-contrast transition hover:opacity-90 disabled:opacity-60"
      >
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}

function errorMessage(response: Response): string {
  if (response.status === 401) return "Wrong password.";
  if (response.status === 429) {
    const minutes = Math.ceil(Number(response.headers.get("retry-after") ?? "900") / 60);
    return `Too many failed attempts. Try again in ${minutes} min.`;
  }
  return "Sign-in failed. Try again.";
}
