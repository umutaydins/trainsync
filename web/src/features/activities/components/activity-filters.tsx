import { useTranslations } from "next-intl";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import type { ActivityFilters } from "@/features/activities/query";
import { useActivityFormat } from "@/features/activities/use-activity-format";

/** Plain GET form: filters end up in the URL and work without JavaScript. */
export function ActivityFiltersForm({ filters, sports }: { filters: ActivityFilters; sports: string[] }) {
  const t = useTranslations("activities.filters");
  const common = useTranslations("common.actions");
  const fmt = useActivityFormat();
  return (
    <form
      method="get"
      action="/activities"
      aria-label={t("label")}
      className="mb-4 grid grid-cols-2 items-end gap-3 rounded-card border border-border bg-surface p-3 shadow-card sm:flex sm:flex-wrap"
    >
      <Field label={t("from")}>
        <Input name="from" type="date" defaultValue={filters.from} />
      </Field>
      <Field label={t("to")}>
        <Input name="to" type="date" defaultValue={filters.to} />
      </Field>
      <Field label={t("sport")} className="col-span-2 sm:w-48">
        <Select name="sport_type" defaultValue={filters.sport_type ?? ""}>
          <option value="">{t("all")}</option>
          {sports.map((sport) => (
            <option key={sport} value={sport}>
              {fmt.sport(sport)}
            </option>
          ))}
        </Select>
      </Field>
      <div className="col-span-2 flex gap-2">
        <Button type="submit">{common("apply")}</Button>
        <Button asChild variant="secondary">
          <Link href="/activities">{common("clear")}</Link>
        </Button>
      </div>
    </form>
  );
}
