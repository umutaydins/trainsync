import { Link2, RefreshCw } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Empty } from "@/components/ui/states";

/** Why the list is empty: the filters, no Strava connection yet, or no synced activities yet. */
export type EmptyReason = "filtered" | "noStrava" | "notSynced";

export function ActivitiesEmpty({ reason }: { reason: EmptyReason }) {
  const t = useTranslations("activities.empty");
  if (reason === "noStrava") {
    return (
      <Empty
        title={t("noStrava")}
        action={
          <Button asChild>
            <Link href="/me/connections">
              <Link2 aria-hidden />
              {t("connect")}
            </Link>
          </Button>
        }
      >
        {t("noStravaHint")}
      </Empty>
    );
  }
  if (reason === "notSynced") {
    return (
      <Empty
        title={t("notSynced")}
        action={
          <Button asChild variant="secondary">
            <Link href="/sync">
              <RefreshCw aria-hidden />
              {t("toSync")}
            </Link>
          </Button>
        }
      >
        {t("notSyncedHint")}
      </Empty>
    );
  }
  return <Empty title={t("filtered")}>{t("filteredHint")}</Empty>;
}
