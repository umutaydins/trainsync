import { useTranslations } from "next-intl";
import Link from "next/link";

import type { Activity } from "@/lib/types";
import { useActivityFormat } from "@/features/activities/use-activity-format";

const TH = "px-3 py-2.5 text-label font-semibold uppercase tracking-[0.08em] text-muted";
const TD = "whitespace-nowrap px-3 py-3";

/** Activities as a table; on phones only date, name, distance and time (the rest on wider screens). */
export function ActivityTable({ items }: { items: Activity[] }) {
  const t = useTranslations("activities.list");
  const fmt = useActivityFormat();
  return (
    <div className="overflow-x-auto rounded-card border border-border bg-surface shadow-card">
      <table className="w-full text-left text-sm" data-testid="activity-table">
        <caption className="sr-only">{t("caption")}</caption>
        <thead className="border-b border-border">
          <tr>
            <th scope="col" className={`${TH} hidden sm:table-cell`}>{t("date")}</th>
            <th scope="col" className={TH}>{t("name")}</th>
            <th scope="col" className={`${TH} hidden md:table-cell`}>{t("sport")}</th>
            <th scope="col" className={`${TH} text-right`}>{t("distance")}</th>
            <th scope="col" className={`${TH} text-right`}>{t("time")}</th>
            <th scope="col" className={`${TH} hidden text-right sm:table-cell`}>{t("effort")}</th>
            <th scope="col" className={`${TH} hidden text-right lg:table-cell`}>{t("elevation")}</th>
            <th scope="col" className={`${TH} hidden text-right lg:table-cell`}>{t("hr")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border tabular">
          {items.map((a) => (
            <tr key={a.id} className="transition hover:bg-surface-2/60" data-activity-id={a.id}>
              <td className={`${TD} hidden text-muted sm:table-cell`}>
                <time dateTime={a.start_date}>{fmt.dateTime(a.start_date)}</time>
              </td>
              <td className="max-w-[12rem] px-3 py-3 sm:max-w-[16rem]">
                <Link href={`/activities/${a.id}`} className="block truncate font-semibold hover:text-accent-ink">
                  {a.name}
                </Link>
                <span className="block truncate text-xs text-muted sm:hidden">
                  {fmt.sport(a.sport_type)} · <time dateTime={a.start_date}>{fmt.dateTime(a.start_date)}</time>
                </span>
              </td>
              <td className={`${TD} hidden md:table-cell`}>{fmt.sport(a.sport_type)}</td>
              <td className={`${TD} text-right`}>{fmt.km(a.distance_m)}</td>
              <td className={`${TD} text-right`}>{fmt.clock(a.moving_time_s)}</td>
              <td className={`${TD} hidden text-right sm:table-cell`}>{fmt.effort(a)}</td>
              <td className={`${TD} hidden text-right lg:table-cell`}>{fmt.meters(a.elevation_gain_m)}</td>
              <td className={`${TD} hidden text-right lg:table-cell`}>{fmt.heartrate(a.average_heartrate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
