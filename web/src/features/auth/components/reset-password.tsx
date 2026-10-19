import Link from "next/link";
import { useTranslations } from "next-intl";

import { buttonVariants } from "@/components/ui/button";
import { Failure } from "@/components/ui/states";
import { ResetForm } from "@/features/auth/components/reset-form";

/** The reset page body: the form for a link's token, or what to do without one. */
export function ResetPassword({ token }: { token: string | null }) {
  const t = useTranslations("auth");
  if (!token) {
    return (
      <div className="flex flex-col gap-6">
        <Failure title={t("reset.errors.invalidLink")} message={t("reset.missingToken")} />
        <Link href="/forgot-password" className={buttonVariants({ variant: "secondary", size: "lg", block: true })}>
          {t("login.forgot")}
        </Link>
      </div>
    );
  }
  return <ResetForm token={token} />;
}
