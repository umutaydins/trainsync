import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Stat } from "@/components/ui/stat";
import { useActivityFormat } from "@/features/activities/use-activity-format";
import { paceKind } from "@/lib/format";
import type { Activity } from "@/lib/types";

export function ActivityDetailCard({ activity: a }: { activity: Activity }) {
  const t = useTranslations("activities.detail");
  const fmt = useActivityFormat();
  const stats: [string, string][] = [
    [t("distance"), fmt.km(a.distance_m)],
    [t("moving"), fmt.clock(a.moving_time_s)],
    [paceKind(a.sport_type) === "speed" ? t("speed") : t("pace"), fmt.effort(a)],
    [t("elevation"), fmt.meters(a.elevation_gain_m)],
    [t("elapsed"), fmt.clock(a.elapsed_time_s)],
    [t("hr"), fmt.heartrate(a.average_heartrate)],
  ];
  return (
    <Card aria-labelledby="activity-title" data-testid="activity-detail" className="p-5 sm:p-7">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="accent">{fmt.sport(a.sport_type)}</Badge>
        <time dateTime={a.start_date} className="text-sm text-muted">
          {fmt.dateTime(a.start_date)}
        </time>
      </div>
      <h1 id="activity-title" className="mt-2 text-3xl font-black tracking-tight sm:text-4xl">
        {a.name}
      </h1>
      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3">
        {stats.map(([label, value]) => (
          <Stat key={label} label={label} value={value} />
        ))}
      </dl>
      <p className="mt-6 border-t border-border pt-4 text-xs text-muted">{t("footer", { id: a.id, time: fmt.dateTime(a.synced_at) })}</p>
    </Card>
  );
}
