import Link from "next/link";

import { EmptyState } from "@/components/ui";
import { formatDate } from "@/lib/format";
import type { CurrentRecord } from "@/features/training/types";
import { PR_LABELS, describeRecord } from "@/features/training/types";

/** Standing records by exercise (`GET /v1/training/prs`). */
export function PrBoard({ records }: { records: CurrentRecord[] }) {
  if (records.length === 0) return <EmptyState title="No records yet">Log a workout to start the board.</EmptyState>;
  const byExercise = new Map<string, CurrentRecord[]>();
  for (const r of records) byExercise.set(r.exercise_name, [...(byExercise.get(r.exercise_name) ?? []), r]);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm tabular-nums" data-testid="pr-board">
        <caption className="sr-only">Personal records</caption>
        <thead className="text-xs text-muted">
          <tr>
            <th scope="col" className="py-1.5 pr-3 font-medium">Exercise</th>
            <th scope="col" className="py-1.5 pr-3 font-medium">Record</th>
            <th scope="col" className="py-1.5 pr-3 text-right font-medium">Value</th>
            <th scope="col" className="py-1.5 text-right font-medium">When</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {[...byExercise.entries()].map(([name, list]) =>
            list.map((r, i) => (
              <tr key={`${r.exercise_id}-${r.kind}-${r.reps ?? ""}`} data-exercise={r.exercise_id} data-kind={r.kind} data-value={r.value} data-reps={r.reps ?? ""}>
                <th scope="row" className="py-1.5 pr-3 font-medium">
                  {i === 0 ? (
                    <Link href={`/training/progress?exercise=${r.exercise_id}`} className="hover:text-accent">
                      {name}
                    </Link>
                  ) : (
                    <span className="sr-only">{name}</span>
                  )}
                </th>
                <td className="py-1.5 pr-3 text-muted">{PR_LABELS[r.kind]}</td>
                <td className="py-1.5 pr-3 text-right font-semibold">{describeRecord(r)}</td>
                <td className="py-1.5 text-right text-xs text-muted">
                  <Link href={`/training/history/${r.workout_id}`} className="hover:text-accent">
                    {formatDate(r.achieved_at)}
                  </Link>
                </td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  );
}
