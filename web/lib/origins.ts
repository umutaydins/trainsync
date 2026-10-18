/**
 * Origins allowed to send mutations through the BFF (CSRF check, ADR 0011): the dashboard's own
 * public URL plus, on Vercel, the exact URLs Vercel gives this deployment (P7.6). No wildcard:
 * a preview of this project is accepted because Vercel tells the deployment its own hostnames
 * (`VERCEL_URL`, `VERCEL_BRANCH_URL`, `VERCEL_PROJECT_PRODUCTION_URL`), so another project, a
 * lookalike domain or plain http never matches.
 */
type Env = Readonly<Record<string, string | undefined>>;

const VERCEL_HOSTS = ["VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"] as const;
// Hostnames only, as Vercel sets them (no scheme, port or path).
const HOSTNAME = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$/;

export function allowedOrigins(publicWebUrl: string, env: Env): string[] {
  const origins = new Set<string>();
  const own = originOf(publicWebUrl);
  if (own) origins.add(own);
  for (const name of VERCEL_HOSTS) {
    const host = env[name]?.trim().toLowerCase();
    if (host && HOSTNAME.test(host)) origins.add(`https://${host}`);
  }
  return [...origins];
}

export function originOf(url: string): string | null {
  try {
    const { origin } = new URL(url);
    return origin === "null" ? null : origin;
  } catch {
    return null;
  }
}
