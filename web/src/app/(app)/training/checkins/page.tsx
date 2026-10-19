import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";

import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { PageTitle } from "@/components/ui/page-header";
import { checkinsApi } from "@/features/checkins/api";
import { dayLabel } from "@/features/checkins/checkins";
import { CheckinDayEditor } from "@/features/checkins/components/day-editor";
import { CheckinHeatmap } from "@/features/checkins/components/heatmap";
import { CheckinTiles } from "@/features/checkins/components/tiles";
import { LoadFailed } from "@/features/shell/components/load-failed";
import { load } from "@/lib/api";

export const dynamic = "force-dynamic";

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("checkins");
  return { title: t("title") };
}

export default async function CheckinsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const [t, locale] = await Promise.all([getTranslations("checkins"), getLocale()]);
  const [list, summary] = await Promise.all([load(() => checkinsApi.list()), load(() => checkinsApi.summary())]);
  if (!list.ok) {
    return (
      <>
        <PageTitle title={t("title")} />
        <LoadFailed title={t("failed")} status={list.status} />
      </>
    );
  }
  const today = summary.ok ? summary.data.today : list.data.to;
  const wanted = typeof params.day === "string" && DAY.test(params.day) ? params.day : today;
  const selected = wanted >= list.data.from && wanted <= list.data.to ? wanted : today;
  const day = await load(() => checkinsApi.day(selected));
  const range = `${dayLabel(locale, list.data.from)} – ${dayLabel(locale, list.data.to)}`;
  return (
    <>
      <PageTitle title={t("title")} subtitle={t("subtitle", { range })} />
      <div className="flex flex-col gap-4">
        {summary.ok ? <CheckinTiles summary={summary.data} /> : <LoadFailed title={t("summaryFailed")} status={summary.status} />}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[auto_1fr]">
          <Card aria-labelledby="calendar-title" className="overflow-x-auto">
            <CardHeader>
              <CardTitle id="calendar-title">{t("calendar")}</CardTitle>
            </CardHeader>
            <CheckinHeatmap from={list.data.from} to={list.data.to} items={list.data.items} selected={selected} />
          </Card>
          <Card>
            {day.ok ? <CheckinDayEditor key={selected} day={selected} checkin={day.data} /> : <LoadFailed title={t("dayFailed")} status={day.status} />}
          </Card>
        </div>
      </div>
    </>
  );
}
