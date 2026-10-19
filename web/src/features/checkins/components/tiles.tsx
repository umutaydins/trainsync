import { useLocale, useTranslations } from "next-intl";

import { Card } from "@/components/ui/card";
import { Stat } from "@/components/ui/stat";
import type { CheckinSummary } from "@/features/checkins/checkins";
import { formatAdherence } from "@/features/checkins/checkins";

/** Streak and adherence (P6.9). */
export function CheckinTiles({ summary }: { summary: CheckinSummary }) {
  const t = useTranslations("checkins.tiles");
  const locale = useLocale();
  return (
    <Card>
      <dl aria-label={t("label")} data-testid="checkin-tiles" className="grid grid-cols-2 gap-4">
        <Stat
          label={t("streak")}
          value={summary.current_streak}
          unit={t("days", { count: summary.current_streak })}
          hint={t("longest", { count: summary.longest_streak })}
        />
        <Stat
          label={t("adherence")}
          value={formatAdherence(locale, summary)}
          hint={summary.adherence === null ? t("noProgram") : t("ofPlanned", { done: summary.planned_days_done, planned: summary.planned_days })}
        />
      </dl>
    </Card>
  );
}
