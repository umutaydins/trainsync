import "server-only";

/**
 * Web secrets that docker-compose.yml gives a DEV-ONLY default (`${VAR:-dev-…}`). The defaults are
 * labelled, so they are found by their `dev-` prefix rather than by a copy of the values. A
 * production server still using one logs a warning at startup (instrumentation.ts).
 */
export const DEV_ONLY_WEB_SECRETS = ["DASHBOARD_SESSION_SECRET"] as const;

const DEV_ONLY_PREFIX = "dev-";

type Env = Readonly<Record<string, string | undefined>>;

/** Names (never values) of web secrets still at a compose dev default. */
export function devSecretsInUse(env: Env): string[] {
  return DEV_ONLY_WEB_SECRETS.filter((name) => env[name]?.startsWith(DEV_ONLY_PREFIX) ?? false);
}

/** In production, warn once about dev defaults; returns the names it warned about. */
export function warnDevSecrets(env: Env, warn: (message: string) => void = console.warn): string[] {
  if (env.NODE_ENV !== "production") return [];
  const names = devSecretsInUse(env);
  if (names.length > 0) {
    warn(
      `trainsync web: ${names.join(", ")} still use the DEV-ONLY docker-compose defaults; ` +
        "set your own values in .env",
    );
  }
  return names;
}
