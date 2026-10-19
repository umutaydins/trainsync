import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { PageTitle } from "@/components/ui/page-header";
import { Failure } from "@/components/ui/states";
import { adminApi, ownerOnly } from "@/features/admin/api";
import { InvitesPanel } from "@/features/admin/components/invites-panel";
import { UsersPanel } from "@/features/admin/components/users-panel";
import { load } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("admin");
  return { title: t("title") };
}

/** `/admin`, the owner's page: invites and accounts. Not found for everyone else. */
export default async function AdminPage() {
  const t = await getTranslations("admin");
  const me = await ownerOnly();
  if (!me.ok) {
    return (
      <>
        <PageTitle title={t("title")} />
        <Failure title={t("loadFailed")} message={me.error} />
      </>
    );
  }
  const [invites, users] = await Promise.all([load(adminApi.invites), load(adminApi.users)]);
  return (
    <div className="flex flex-col gap-5">
      <PageTitle title={t("title")} subtitle={t("subtitle")} />
      <div className="grid items-start gap-5 lg:grid-cols-2">
        {invites.ok ? (
          <InvitesPanel initial={invites.data.items} />
        ) : (
          <Failure title={t("invites.loadFailed")} message={invites.error} />
        )}
        {users.ok ? <UsersPanel users={users.data.items} /> : <Failure title={t("users.loadFailed")} message={users.error} />}
      </div>
    </div>
  );
}
