import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Select } from "@/components/ui/input";
import { PageTitle } from "@/components/ui/page-header";
import { Empty } from "@/components/ui/states";
import { LoadFailed } from "@/features/shell/components/load-failed";
import { PrBoard } from "@/features/training/components/pr-board";
import { BodyWeightChart, ExerciseProgressChart, WeeklyMuscleChart } from "@/features/training/components/progress-charts";
import type { BodyMetricList, Exercise, ExerciseProgress, RecordList, WeeklyVolume } from "@/features/training/types";
import type { Loaded } from "@/lib/api";

export interface LiftsData {
  exercises: Exercise[];
  exerciseId: number | null;
  progress: Loaded<ExerciseProgress> | null;
  records: Loaded<RecordList>;
  weekly: Loaded<WeeklyVolume>;
  weights: Loaded<BodyMetricList>;
}

function Block({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <Card aria-labelledby={id}>
      <CardHeader>
        <CardTitle id={id}>{title}</CardTitle>
      </CardHeader>
      {children}
    </Card>
  );
}

/** `/training/progress`: e1RM and best set per exercise, weekly muscle volume, records, body weight. */
export function LiftsView({ data }: { data: LiftsData }) {
  const t = useTranslations("training.lifts");
  const records = useTranslations("training.records");
  const { progress, weekly, weights } = data;
  return (
    <div className="flex flex-col gap-4">
      <PageTitle title={t("title")} subtitle={t("subtitle")} />
      <Block id="exercise-title" title={t("exercise")}>
        {data.exercises.length > 0 ? (
          <form method="get" className="mb-4 flex items-end gap-2">
            <Field label={t("exercise")} className="flex-1">
              <Select name="exercise" defaultValue={data.exerciseId ?? undefined}>
                {data.exercises.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Button type="submit">{t("show")}</Button>
          </form>
        ) : null}
        {progress === null ? (
          <Empty title={t("noExercise")}>{t("noExerciseHint")}</Empty>
        ) : !progress.ok ? (
          <LoadFailed title={t("failed")} status={progress.status} />
        ) : progress.data.sessions.length === 0 ? (
          <Empty title={t("noSets", { name: progress.data.exercise.name })} />
        ) : (
          <ExerciseProgressChart progress={progress.data} />
        )}
      </Block>

      <Block id="muscle-title" title={t("muscleTitle")}>
        {!weekly.ok ? (
          <LoadFailed title={t("muscleFailed")} status={weekly.status} />
        ) : weekly.data.items.length === 0 ? (
          <Empty title={t("muscleEmpty")} />
        ) : (
          <WeeklyMuscleChart items={weekly.data.items} />
        )}
      </Block>

      <Block id="records-title" title={records("title")}>
        {data.records.ok ? <PrBoard records={data.records.data.items} /> : <LoadFailed title={records("failed")} status={data.records.status} />}
      </Block>

      {weights.ok && weights.data.items.length > 0 ? (
        <Block id="weight-title" title={t("weight")}>
          <BodyWeightChart items={weights.data.items} />
        </Block>
      ) : null}
    </div>
  );
}
