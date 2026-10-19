"use client";

import { Flag, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Empty, Failure } from "@/components/ui/states";
import { isBackendDown } from "@/features/shell/components/load-failed";
import { restOver } from "@/features/training/alerts";
import { ExerciseCard } from "@/features/training/components/exercise-card";
import { ExercisePickerSheet } from "@/features/training/components/exercise-picker";
import { PlateSheet } from "@/features/training/components/plate-sheet";
import { RestTimerPanel } from "@/features/training/components/rest-timer";
import { WorkoutHeader } from "@/features/training/components/workout-header";
import { WorkoutFinished } from "@/features/training/components/workout-summary";
import { type KeyValueStore, type Now, adjustRest, browserStorage, systemNow } from "@/features/training/timers";
import type { Exercise, WorkoutDetail } from "@/features/training/types";
import { type Finish, type Send, useWorkout } from "@/features/training/use-workout";
import { useWorkoutClock } from "@/features/training/use-workout-clock";
import { useWakeLock } from "@/features/training/wake-lock";
import { newClientId } from "@/features/training/workout-rows";
import { post, put } from "@/lib/mutate";

export interface WorkoutScreenProps {
  initial: WorkoutDetail;
  exercises: Exercise[];
  /** Test seams. */
  now?: Now;
  store?: KeyValueStore | null;
  send?: Send;
  finish?: Finish;
  newId?: () => string;
}

const defaultSend: Send = (path, body) => put<unknown>(path, body);
const defaultFinish: Finish = (id) => post<WorkoutDetail>(`/v1/training/workouts/${id}/finish`, {});

/**
 * The active-workout screen (P6.6, P8.16), one-handed: the next set big with −/+ steppers and a
 * one-tap "Set done", a full-screen rest timer, the plate calculator in a bottom sheet, a summary
 * at the end. Rendered on the client only (localStorage and the clock on its first render).
 */
export function WorkoutScreen({
  initial,
  exercises,
  now = systemNow,
  store = browserStorage(),
  send = defaultSend,
  finish = defaultFinish,
  newId = newClientId,
}: WorkoutScreenProps) {
  const t = useTranslations("workout");
  const restLabel = (exercise: string, setIndex: number) => t("rest.label", { exercise, index: setIndex });
  const workout = useWorkout({ initial, exercises, now, store, send, finish, newId, restLabel });
  const { local, groups, summary } = workout;
  const { clock, sync } = useWorkoutClock({
    rest: local.rest,
    now,
    onRestOver: (rest) => restOver(t("rest.over"), t("rest.next", { label: rest.label })),
    markAlerted: () => workout.updateRest((rest) => ({ ...rest, alerted: true })),
  });
  const wakeLock = useWakeLock(summary === null);
  const [plates, setPlates] = useState<{ kg: number; name: string } | null>(null);
  const [picking, setPicking] = useState(false);

  if (summary) return <WorkoutFinished workout={summary} />;

  // The set to do next, shown big: the first one not logged (or on its way), in workout order.
  const current = groups.flatMap((g) => g.rows).find((r) => r.status === "idle" || r.status === "error") ?? null;
  const error = workout.finishError;

  return (
    <div className="flex flex-col gap-4 pb-32" data-testid="workout-screen">
      <WorkoutHeader startedAt={initial.started_at} clock={clock} rows={local.rows} queued={workout.queued} screenOn={wakeLock === "active"} />

      {groups.length === 0 ? <Empty title={t("empty")} /> : null}
      {groups.map((group) => (
        <ExerciseCard
          key={group.exerciseId}
          group={group}
          currentId={current?.clientId ?? null}
          onChange={workout.updateRow}
          onLog={(row) => void workout.logSet(group, row)}
          onAddSet={() => workout.addSet(group)}
          onPlates={(kg) => setPlates({ kg, name: group.name })}
        />
      ))}

      <Button variant="outline" size="lg" block onClick={() => setPicking(true)}>
        <Plus aria-hidden />
        {t("addExercise")}
      </Button>

      {error ? (
        <Failure
          title={t("finishFailed")}
          message={error.kind === "pending" ? t("pending", { count: error.count }) : isBackendDown(error.status) ? t("offline") : undefined}
        />
      ) : null}
      <Button size="lg" block onClick={() => void workout.onFinish()} disabled={workout.finishing}>
        <Flag aria-hidden />
        {workout.finishing ? t("finishing") : t("finish")}
      </Button>

      {local.rest ? (
        <RestTimerPanel
          rest={local.rest}
          now={clock}
          onAdjust={(delta) => {
            workout.updateRest((rest) => adjustRest(rest, delta, now()));
            sync();
          }}
          onSkip={() => workout.updateRest(() => null)}
        />
      ) : null}

      <PlateSheet target={plates} onClose={() => setPlates(null)} />
      <ExercisePickerSheet
        open={picking}
        onOpenChange={setPicking}
        exercises={exercises}
        onPick={(exercise) => {
          setPicking(false);
          workout.addExercise(exercise);
        }}
      />
    </div>
  );
}
