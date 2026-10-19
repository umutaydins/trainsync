import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AuthLayout } from "@/features/auth/components/auth-layout";
import { LoginForm } from "@/features/auth/components/login-form";
import { SuccessNotice } from "@/features/auth/components/notice";
import { safeNextPath } from "@/lib/session";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auth.login");
  return { title: t("metaTitle") };
}

/** `/login?next=<path>` (where to go after), `reset=1` after a password reset. */
export default async function LoginPage({ searchParams }: { searchParams: SearchParams }) {
  const { next, reset } = await searchParams;
  const t = await getTranslations("auth.login");
  return (
    <AuthLayout title={t("title")} subtitle={t("subtitle")}>
      {reset === "1" ? <SuccessNotice>{t("resetDone")}</SuccessNotice> : null}
      <LoginForm next={safeNextPath(typeof next === "string" ? next : undefined)} />
    </AuthLayout>
  );
}
