import type { Locale } from "@/i18n/config";

/**
 * One message file per feature and language (ADR 0039), merged under its namespace:
 * `messages/<locale>/<namespace>.json` → `t("<namespace>.<key>")`. Add a namespace here and in
 * both languages; tests/i18n.test.ts checks that the key sets match.
 */
export const NAMESPACES = ["common", "nav", "auth", "onboarding", "legal"] as const;
export type Namespace = (typeof NAMESPACES)[number];

export type Messages = Record<Namespace, Record<string, unknown>>;

export async function loadMessages(locale: Locale): Promise<Messages> {
  const entries = await Promise.all(
    NAMESPACES.map(async (namespace) => {
      const file = (await import(`./${locale}/${namespace}.json`)) as { default: Record<string, unknown> };
      return [namespace, file.default] as const;
    }),
  );
  return Object.fromEntries(entries) as Messages;
}
