import "server-only";

import { allowedOrigins } from "@/lib/origins";
import { cookieSecureFromEnv } from "@/lib/session";

/** Server-only configuration. Read per call so tests and the runtime can change it. */
export interface ServerEnv {
  /** Base URL the server uses to reach the trainsync API (inside compose: http://api:8000). */
  apiUrl: string;
  /** Seals the session cookie that carries the user's API token (ADR 0034). */
  sessionSecret: string;
  cookieSecure: boolean;
  /**
   * Browser-facing base URL of this web app: the OAuth `return_to`, and the only origin allowed to
   * send mutations through the BFF (CSRF check, ADR 0011).
   */
  publicWebUrl: string;
  /** Origins whose mutations the BFF accepts: `publicWebUrl` plus this Vercel deployment's URLs. */
  allowedOrigins: string[];
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
  const publicWebUrl = withoutTrailingSlash(process.env.WEB_PUBLIC_URL || "http://localhost:3000");
  return {
    apiUrl: withoutTrailingSlash(process.env.TRAINSYNC_API_URL || "http://localhost:8000"),
    sessionSecret,
    cookieSecure: cookieSecureFromEnv(),
    publicWebUrl,
    allowedOrigins: allowedOrigins(publicWebUrl, process.env),
  };
}
