import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AuthLayout } from "@/features/auth/components/auth-layout";
import { Registration } from "@/features/auth/components/register-form";
import { registrationMode } from "@/features/auth/registration";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auth.register");
  return { title: t("metaTitle") };
}

/**
 * `/register`, or `/register?invite=<code>` (the links the API builds): the form for the API's
 * registration mode (invite code, open, or closed).
 */
export default async function RegisterPage({ searchParams }: { searchParams: SearchParams }) {
  const [{ invite }, t, mode] = await Promise.all([
    searchParams,
    getTranslations("auth.register"),
    registrationMode(),
  ]);
  const code = typeof invite === "string" ? invite : "";
  return (
    <AuthLayout title={code ? t("inviteTitle") : t("title")} subtitle={t("subtitle")}>
      <Registration mode={mode} inviteCode={code} />
    </AuthLayout>
  );
}
