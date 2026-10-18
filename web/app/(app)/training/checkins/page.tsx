import type { Metadata } from "next";

import { CheckinDayEditor } from "@/components/checkins/day-editor";
import { CheckinHeatmap } from "@/components/checkins/heatmap";
import { CheckinTiles } from "@/components/checkins/tiles";
import { Card, ErrorState, PageHeader } from "@/components/ui";
import { load } from "@/lib/api";
import { dayLabel } from "@/lib/checkins";
import { checkinsApi } from "@/lib/checkins-api";

export const metadata: Metadata = { title: "Check-ins" };
export const dynamic = "force-dynamic";

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export default async function CheckinsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const [list, summary] = await Promise.all([
    load(() => checkinsApi.list()),
    load(() => checkinsApi.summary()),
  ]);
  if (!list.ok) {
    return (
      <>
        <PageHeader title="Check-ins" />
        <ErrorState title="Could not load check-ins" message={list.error} />
      </>
    );
  }
  const today = summary.ok ? summary.data.today : list.data.to;
  const wanted = typeof params.day === "string" && DAY.test(params.day) ? params.day : today;
  const selected = wanted >= list.data.from && wanted <= list.data.to ? wanted : today;
  const day = await load(() => checkinsApi.day(selected));
  return (
    <>
      <PageHeader
        title="Check-ins"
        subtitle={`${dayLabel(list.data.from)} – ${dayLabel(list.data.to)} · answered in Telegram every evening`}
      />
      <div className="space-y-4">
        {summary.ok ? (
          <CheckinTiles summary={summary.data} />
        ) : (
          <ErrorState title="Could not load streak and adherence" message={summary.error} />
        )}
        <div className="grid gap-4 lg:grid-cols-[auto_1fr]">
          <Card title="Calendar" labelledBy="calendar-title">
            <CheckinHeatmap from={list.data.from} to={list.data.to} items={list.data.items} selected={selected} />
          </Card>
          <Card>
            {day.ok ? (
              <CheckinDayEditor key={selected} day={selected} checkin={day.data} />
            ) : (
              <ErrorState title="Could not load the day" message={day.error} />
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
