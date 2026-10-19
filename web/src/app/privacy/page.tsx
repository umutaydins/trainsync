import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { AuthLayout } from "@/features/auth/components/auth-layout";
import { LegalDocument } from "@/features/legal/components/legal-document";
import { ownerContactEmail } from "@/lib/env";

export const dynamic = "force-dynamic";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("legal.privacy");
  return { title: t("metaTitle") };
}

export default async function PrivacyPage() {
  const t = await getTranslations("legal.privacy");
  return (
    <AuthLayout title={t("title")} subtitle={t("subtitle")} wide>
      <LegalDocument doc="privacy" email={ownerContactEmail()} />
    </AuthLayout>
  );
}
