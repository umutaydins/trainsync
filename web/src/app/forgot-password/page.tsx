import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AuthLayout } from "@/features/auth/components/auth-layout";
import { ForgotPassword } from "@/features/auth/components/forgot-password";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auth.forgot");
  return { title: t("metaTitle") };
}

export default async function ForgotPasswordPage() {
  const t = await getTranslations("auth.forgot");
  return (
    <AuthLayout title={t("title")} subtitle={t("subtitle")}>
      <ForgotPassword />
    </AuthLayout>
  );
}
