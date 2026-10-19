import { Dumbbell, Link2, UtensilsCrossed } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import type { ReactNode } from "react";

import { buttonVariants } from "@/components/ui/button";
import { PageTitle } from "@/components/ui/page-header";
import { Empty } from "@/components/ui/states";
import { Block, BlockFailure } from "@/features/progress/components/block";
import { EnduranceBlock } from "@/features/progress/components/endurance-block";
import { BodyBlock, ConsistencyBlock, NutritionBlock } from "@/features/progress/components/habit-blocks";
import { KcalChart } from "@/features/progress/components/kcal-chart";
import { LiftsBlock } from "@/features/progress/components/lifts-block";
import { PeriodSwitcher } from "@/features/progress/components/period-switcher";
import { StrengthBlock } from "@/features/progress/components/strength-block";
import { VolumeChart } from "@/features/progress/components/volume-chart";
import { WeightChart } from "@/features/progress/components/weight-chart";
import { YearHeatmap } from "@/features/progress/components/year-heatmap";
import { formatWindow } from "@/features/progress/format";
import { type ProgressData, isFresh } from "@/features/progress/load";
import type { Period, ProgressSummary, Series } from "@/features/progress/types";
import type { Loaded } from "@/lib/api";

/** `/progress`: the period switcher, then one block per area, each with its own error state. */
export function ProgressView({ data }: { data: ProgressData }) {
  const t = useTranslations("progress");
  const locale = useLocale();
  const { query, summary } = data;
  const period = query.period;
  const subtitle = summary.ok ? windowText(summary.data, locale, t("vs")) : null;
  const ok = (result: Loaded<Series>) => (result.ok ? result.data : null);

  return (
    <div className="flex flex-col gap-4" data-testid="progress" data-period={period}>
      <PageTitle title={t("title")} subtitle={subtitle} />
      <PeriodSwitcher query={query} today={data.today} />
      {isFresh(data) ? (
        <FreshEmpty />
      ) : (
        <>
          <Block id="volume" title={t("volume.title")} period={period}>
            {!data.distance.ok && !data.tonnage.ok ? (
              <BlockFailure error={data.distance.error} />
            ) : (
              <VolumeChart distance={ok(data.distance)} tonnage={ok(data.tonnage)} />
            )}
          </Block>
          {/* Two balanced columns on desktop, each card at its own height (no card stretched to
              its neighbour's); one column, in this order, on phones. */}
          <div data-testid="progress-blocks" className="flex flex-col gap-4 lg:block lg:columns-2 lg:gap-4 lg:[&>*]:mb-4 lg:[&>*]:break-inside-avoid">
            <SummaryBlock summary={summary} id="endurance" title={t("endurance.title")} period={period}>
              {(s) => <EnduranceBlock endurance={s.endurance} period={period} />}
            </SummaryBlock>
            <SummaryBlock summary={summary} id="strength" title={t("strength.title")} period={period}>
              {(s) => <StrengthBlock strength={s.strength} period={period} />}
            </SummaryBlock>
            <LiftsBlock
              allRecords={data.allPrs}
              periodRecords={data.prs}
              exercises={summary.ok ? summary.data.strength.by_exercise : []}
              query={query}
            />
            <SummaryBlock summary={summary} id="consistency" title={t("consistency.title")} period={period}>
              {(s) => (
                <ConsistencyBlock consistency={s.consistency} period={period}>
                  <HeatmapPart data={data} />
                </ConsistencyBlock>
              )}
            </SummaryBlock>
            <SummaryBlock summary={summary} id="nutrition" title={t("nutrition.title")} period={period}>
              {(s) => (
                <NutritionBlock nutrition={s.nutrition} period={period}>
                  {data.kcal.ok ? <KcalChart series={data.kcal.data} /> : <BlockFailure error={data.kcal.error} />}
                </NutritionBlock>
              )}
            </SummaryBlock>
            <SummaryBlock summary={summary} id="body" title={t("body.title")} period={period}>
              {(s) => (
                <BodyBlock body={s.body} period={period}>
                  {data.weight.ok ? <WeightChart series={data.weight.data} /> : <BlockFailure error={data.weight.error} />}
                </BodyBlock>
              )}
            </SummaryBlock>
          </div>
        </>
      )}
    </div>
  );
}

function windowText(summary: ProgressSummary, locale: string, vs: string): string {
  const current = formatWindow(locale, summary.window.from, summary.window.to);
  return summary.previous ? `${current} · ${vs} ${formatWindow(locale, summary.previous.from, summary.previous.to)}` : current;
}

/** A block drawn from the summary, or its error state in the same card when the summary failed. */
function SummaryBlock({
  summary,
  id,
  title,
  period,
  children,
}: {
  summary: Loaded<ProgressSummary>;
  id: string;
  title: string;
  period: Period;
  children: (summary: ProgressSummary) => ReactNode;
}) {
  if (summary.ok) return children(summary.data);
  return (
    <Block id={id} title={title} period={period}>
      <BlockFailure error={summary.error} />
    </Block>
  );
}

function HeatmapPart({ data }: { data: ProgressData }) {
  const t = useTranslations("progress.heatmap");
  if (!data.heatmap.ok) return <BlockFailure error={data.heatmap.error} />;
  const thisYear = Number(data.today.slice(0, 4));
  const firstYear = data.allPrs.ok ? Math.min(thisYear, Number(data.allPrs.data.window.from.slice(0, 4))) : thisYear;
  return (
    <section aria-label={t("title")} className="border-t border-border pt-4">
      <YearHeatmap key={data.heatmap.data.rolling ? "rolling" : data.heatmap.data.year} heatmap={data.heatmap.data} today={data.today} firstYear={firstYear} query={data.query} />
    </section>
  );
}

/** A fresh account: the three ways to get numbers here. */
function FreshEmpty() {
  const t = useTranslations("progress.fresh");
  const link = buttonVariants({ variant: "secondary", size: "md", block: true });
  return (
    <Empty title={t("title")} className="bg-surface">
      <p>{t("body")}</p>
      <ul className="mt-4 flex flex-col gap-2">
        <li>
          <Link href="/me/connections" className={link}>
            <Link2 aria-hidden />
            {t("strava")}
          </Link>
        </li>
        <li>
          <Link href="/training" className={link}>
            <Dumbbell aria-hidden />
            {t("workout")}
          </Link>
        </li>
        <li>
          <Link href="/nutrition" className={link}>
            <UtensilsCrossed aria-hidden />
            {t("food")}
          </Link>
        </li>
      </ul>
    </Empty>
  );
}
