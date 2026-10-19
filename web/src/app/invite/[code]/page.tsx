import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AuthLayout } from "@/features/auth/components/auth-layout";
import { Registration } from "@/features/auth/components/register-form";
import { registrationMode } from "@/features/auth/registration";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auth.register");
  return { title: t("metaTitle") };
}

/** `/invite/<code>`: the owner's invite link; the register form with the code filled in. */
export default async function InvitePage({ params }: { params: Promise<{ code: string }> }) {
  const [{ code }, t, mode] = await Promise.all([params, getTranslations("auth.register"), registrationMode()]);
  return (
    <AuthLayout title={t("inviteTitle")} subtitle={t("subtitle")}>
      <Registration mode={mode} inviteCode={code} />
    </AuthLayout>
  );
}
