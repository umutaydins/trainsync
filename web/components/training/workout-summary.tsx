import { Card, StatTile } from "@/components/ui";
import { formatClock, formatDateTime } from "@/lib/format";
import type { WorkoutDetail } from "@/lib/training-types";
import { PR_LABELS, describeRecord, formatVolume } from "@/lib/training-types";

export function workoutDurationS(workout: Pick<WorkoutDetail, "started_at" | "ended_at">): number | null {
  if (!workout.ended_at) return null;
  return Math.max(0, (Date.parse(workout.ended_at) - Date.parse(workout.started_at)) / 1000);
}

/** Duration, total volume, sets and the records this workout set. */
export function WorkoutSummaryCard({ workout }: { workout: WorkoutDetail }) {
  const duration = workoutDurationS(workout);
  return (
    <div className="space-y-4" data-testid="workout-summary" data-volume={workout.volume_kg}>
      <div>
        <h2 className="text-lg font-semibold tracking-tight">{workout.program_day_name ?? "Workout"}</h2>
        <p className="text-sm text-muted">{formatDateTime(workout.started_at)}</p>
      </div>
      <dl className="grid grid-cols-3 gap-2 sm:gap-3">
        <StatTile label="Duration" value={duration === null ? "in progress" : formatClock(duration)} />
        <StatTile label="Volume" value={formatVolume(workout.volume_kg)} />
        <StatTile label="Sets" value={String(workout.set_count)} />
      </dl>
      <Card title={`Records (${workout.records.length})`} labelledBy={`records-${workout.id}`}>
        {workout.records.length === 0 ? (
          <p className="text-sm text-muted">No new records this time.</p>
        ) : (
          <ul className="divide-y divide-border text-sm" data-testid="workout-records">
            {workout.records.map((r, i) => (
              <li key={i} className="flex flex-wrap items-baseline justify-between gap-2 py-2">
                <span className="font-medium">{r.exercise_name}</span>
                <span className="text-muted">
                  {PR_LABELS[r.kind]}: <span className="font-semibold text-text">{describeRecord(r)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
