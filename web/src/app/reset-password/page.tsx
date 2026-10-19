import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AuthLayout } from "@/features/auth/components/auth-layout";
import { ResetPassword } from "@/features/auth/components/reset-password";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auth.reset");
  return { title: t("metaTitle") };
}

/** `/reset-password?token=<token>`: the link the owner's admin endpoint returns. */
export default async function ResetPasswordPage({ searchParams }: { searchParams: SearchParams }) {
  const [{ token }, t] = await Promise.all([searchParams, getTranslations("auth.reset")]);
  return (
    <AuthLayout title={t("title")} subtitle={t("subtitle")}>
      <ResetPassword token={typeof token === "string" && token ? token : null} />
    </AuthLayout>
  );
}
