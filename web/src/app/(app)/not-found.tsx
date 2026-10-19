import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { Button } from "@/components/ui/button";
import { Empty } from "@/components/ui/states";

export default async function NotFound() {
  const t = await getTranslations("common.states");
  return (
    <Empty
      title={t("notFoundTitle")}
      action={
        <Button asChild variant="secondary">
          <Link href="/">{t("notFoundHome")}</Link>
        </Button>
      }
    >
      {t("notFoundBody")}
    </Empty>
  );
}
