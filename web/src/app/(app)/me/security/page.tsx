import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { Failure } from "@/components/ui/states";
import { settingsApi } from "@/features/settings/api";
import { PasswordForm } from "@/features/settings/components/password-form";
import { SessionsList } from "@/features/settings/components/sessions-list";
import { SettingsPage } from "@/features/settings/components/settings-page";
import { load } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("settings.sections.security");
  return { title: t("title") };
}

/** `/me/security`: password and signed-in devices. */
export default async function SecurityPage() {
  const t = await getTranslations("settings");
  const sessions = await load(settingsApi.sessions);
  return (
    <SettingsPage title={t("sections.security.title")} subtitle={t("sections.security.hint")}>
      <PasswordForm />
      {sessions.ok ? (
        // Keyed by the ids, so a refresh after a password change shows the remaining sessions.
        <SessionsList key={sessions.data.items.map((s) => s.id).join(",")} initial={sessions.data.items} />
      ) : (
        <Failure title={t("security.sessionsFailed")} />
      )}
    </SettingsPage>
  );
}
