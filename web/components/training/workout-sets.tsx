import { Card } from "@/components/ui";
import type { Exercise, WorkoutDetail } from "@/lib/training-types";
import { formatKg, formatVolume } from "@/lib/training-types";

/** The logged sets of a workout, grouped by exercise in the order they were first done. */
export function WorkoutSets({ workout, exercises }: { workout: WorkoutDetail; exercises: Map<number, Exercise> }) {
  const names = new Map<number, string>(workout.planned.map((p) => [p.exercise.id, p.exercise.name]));
  for (const r of workout.records) if (r.exercise_name) names.set(r.exercise_id, r.exercise_name);
  const order: number[] = [];
  for (const s of workout.sets) if (!order.includes(s.exercise_id)) order.push(s.exercise_id);

  return (
    <Card title="Sets" labelledBy="sets-title">
      {order.length === 0 ? (
        <p className="text-sm text-muted">No sets were logged.</p>
      ) : (
        <div className="space-y-4" data-testid="workout-sets">
          {order.map((id) => {
            const sets = workout.sets.filter((s) => s.exercise_id === id).sort((a, b) => a.set_index - b.set_index);
            const volume = sets.filter((s) => !s.is_warmup).reduce((sum, s) => sum + s.reps * s.weight_kg, 0);
            const name = names.get(id) ?? exercises.get(id)?.name ?? `Exercise ${id}`;
            return (
              <section key={id} aria-label={name}>
                <h3 className="flex justify-between text-sm font-semibold">
                  <span>{name}</span>
                  <span className="font-normal text-muted tabular-nums">{formatVolume(volume)}</span>
                </h3>
                <ol className="mt-1 flex flex-wrap gap-1.5 text-sm tabular-nums">
                  {sets.map((s) => (
                    <li key={s.client_id} className="rounded-lg bg-surface-2 px-2 py-1">
                      {s.reps} × {formatKg(s.weight_kg)}
                      {s.is_warmup ? <span className="text-xs text-muted"> warm-up</span> : null}
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
