import "server-only";

/** Server-only configuration. Read per call so tests and the runtime can change it. */
export interface ServerEnv {
  /** Base URL the server uses to reach the trainsync API (inside compose: http://api:8000). */
  apiUrl: string;
  /** Sent as `X-API-Key`; never leaves the server. */
  apiKey: string;
  dashboardPassword: string;
  sessionSecret: string;
  cookieSecure: boolean;
  /** Browser-facing base URL of the trainsync API (for the Connect Strava link). */
  publicApiUrl: string;
  /** Browser-facing base URL of this web app (for the OAuth `return_to`). */
  publicWebUrl: string;
}

export class ConfigError extends Error {}

const MIN_SECRET_LENGTH = 32;

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new ConfigError(`${name} is not set`);
  return value;
}

function withoutTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

export function serverEnv(): ServerEnv {
  const sessionSecret = required("DASHBOARD_SESSION_SECRET");
  if (sessionSecret.length < MIN_SECRET_LENGTH) {
    throw new ConfigError(`DASHBOARD_SESSION_SECRET must be at least ${MIN_SECRET_LENGTH} characters`);
  }
  const secureOverride = process.env.DASHBOARD_COOKIE_SECURE;
  return {
    apiUrl: withoutTrailingSlash(process.env.TRAINSYNC_API_URL || "http://localhost:8000"),
    apiKey: required("TRAINSYNC_API_KEY"),
    dashboardPassword: required("DASHBOARD_PASSWORD"),
    sessionSecret,
    cookieSecure: secureOverride
      ? secureOverride === "true"
      : process.env.NODE_ENV === "production",
    publicApiUrl: withoutTrailingSlash(
      process.env.TRAINSYNC_PUBLIC_API_URL || "http://localhost:8000",
    ),
    publicWebUrl: withoutTrailingSlash(process.env.WEB_PUBLIC_URL || "http://localhost:3000"),
  };
}
