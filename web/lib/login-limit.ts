import "server-only";

export const LOGIN_MAX_FAILURES = 5;
export const LOGIN_WINDOW_MS = 15 * 60 * 1000;
// Bounds memory if many addresses fail once; expired windows are dropped first.
const MAX_TRACKED = 10_000;

type Window = { failures: number; resetAt: number };

/**
 * Failed logins per client address in a fixed window that starts at the first failure.
 * In-memory: one `web` process serves the dashboard, and a restart only forgets failures.
 */
export class LoginRateLimiter {
  private readonly windows = new Map<string, Window>();

  constructor(
    private readonly maxFailures = LOGIN_MAX_FAILURES,
    private readonly windowMs = LOGIN_WINDOW_MS,
    private readonly now: () => number = () => Date.now(),
  ) {}

  /** Seconds until `ip` may try again, or null when it is not blocked. */
  retryAfterS(ip: string): number | null {
    const window = this.current(ip);
    if (!window || window.failures < this.maxFailures) return null;
    return Math.max(1, Math.ceil((window.resetAt - this.now()) / 1000));
  }

  recordFailure(ip: string): void {
    const window = this.current(ip);
    if (window) {
      window.failures += 1;
      return;
    }
    if (this.windows.size >= MAX_TRACKED) this.prune();
    this.windows.set(ip, { failures: 1, resetAt: this.now() + this.windowMs });
  }

  reset(ip: string): void {
    this.windows.delete(ip);
  }

  private current(ip: string): Window | undefined {
    const window = this.windows.get(ip);
    if (window && window.resetAt <= this.now()) {
      this.windows.delete(ip);
      return undefined;
    }
    return window;
  }

  private prune(): void {
    const now = this.now();
    for (const [ip, window] of this.windows) if (window.resetAt <= now) this.windows.delete(ip);
    // Still full: forget the oldest entry rather than grow without bound.
    if (this.windows.size >= MAX_TRACKED) {
      const oldest = this.windows.keys().next().value;
      if (oldest !== undefined) this.windows.delete(oldest);
    }
  }
}

export const loginLimiter = new LoginRateLimiter();

/**
 * The client address: the last `X-Forwarded-For` entry. Next.js sets the header from the socket
 * when it is absent, and a reverse proxy in front appends the address it saw, so the last entry
 * is the one the nearest hop vouches for (ADR 0011).
 */
export function clientIp(headers: Headers): string {
  const forwarded = headers.get("x-forwarded-for") ?? "";
  const last = forwarded.split(",").at(-1)?.trim();
  return last || "unknown";
}
