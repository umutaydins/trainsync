import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AuthLayout } from "@/features/auth/components/auth-layout";
import { ResetPassword } from "@/features/auth/components/reset-password";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auth.reset");
  return { title: t("metaTitle") };
}

/** `/reset-password/<token>`: the same page with the token in the path. */
export default async function ResetPasswordTokenPage({ params }: { params: Promise<{ token: string }> }) {
  const [{ token }, t] = await Promise.all([params, getTranslations("auth.reset")]);
  return (
    <AuthLayout title={t("title")} subtitle={t("subtitle")}>
      <ResetPassword token={token} />
    </AuthLayout>
  );
}
