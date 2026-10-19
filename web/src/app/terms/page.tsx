import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AuthLayout } from "@/features/auth/components/auth-layout";
import { LegalDocument } from "@/features/legal/components/legal-document";
import { ownerContactEmail } from "@/lib/env";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("legal.terms");
  return { title: t("metaTitle") };
}

export default async function TermsPage() {
  const t = await getTranslations("legal.terms");
  return (
    <AuthLayout title={t("title")} subtitle={t("subtitle")} wide>
      <LegalDocument doc="terms" email={ownerContactEmail()} />
    </AuthLayout>
  );
}
