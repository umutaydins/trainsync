import { useTranslations } from "next-intl";

import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import type { Exercise, WorkoutDetail } from "@/features/training/types";
import { useTrainingFormat } from "@/features/training/use-training-format";

/** The logged sets of a workout, grouped by exercise in the order they were first done. */
export function WorkoutSets({ workout, exercises }: { workout: WorkoutDetail; exercises: Map<number, Exercise> }) {
  const t = useTranslations("workout.sets");
  const fmt = useTrainingFormat();
  const names = new Map<number, string>(workout.planned.map((p) => [p.exercise.id, p.exercise.name]));
  for (const r of workout.records) if (r.exercise_name) names.set(r.exercise_id, r.exercise_name);
  const order: number[] = [];
  for (const s of workout.sets) if (!order.includes(s.exercise_id)) order.push(s.exercise_id);

  return (
    <Card aria-labelledby="sets-title">
      <CardHeader>
        <CardTitle id="sets-title">{t("title")}</CardTitle>
      </CardHeader>
      {order.length === 0 ? (
        <p className="text-sm text-muted">{t("none")}</p>
      ) : (
        <div className="flex flex-col gap-4" data-testid="workout-sets">
          {order.map((id) => {
            const sets = workout.sets.filter((s) => s.exercise_id === id).sort((a, b) => a.set_index - b.set_index);
            const volume = sets.filter((s) => !s.is_warmup).reduce((sum, s) => sum + s.reps * s.weight_kg, 0);
            const name = names.get(id) ?? exercises.get(id)?.name ?? `#${id}`;
            return (
              <section key={id} aria-label={name}>
                <h3 className="flex justify-between gap-3 font-semibold">
                  <span>{name}</span>
                  <span className="font-normal text-muted tabular">{fmt.volume(volume)}</span>
                </h3>
                <ol className="mt-2 flex flex-wrap gap-1.5 text-sm tabular">
                  {sets.map((s) => (
                    <li key={s.client_id} className="rounded-full bg-surface-2 px-3 py-1">
                      {s.reps} × {fmt.kg(s.weight_kg)}
                      {s.is_warmup ? <span className="text-xs text-muted"> {t("warmup")}</span> : null}
                    </li>
                  ))}
                </ol>
              </section>
            );
          })}
        </div>
      )}
    </Card>
  );
}
