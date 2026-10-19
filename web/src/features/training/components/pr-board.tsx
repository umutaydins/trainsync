import { useTranslations } from "next-intl";
import Link from "next/link";

import { Empty } from "@/components/ui/states";
import type { CurrentRecord } from "@/features/training/types";
import { useTrainingFormat } from "@/features/training/use-training-format";

/** Standing records by exercise (`GET /v1/training/prs`). */
export function PrBoard({ records }: { records: CurrentRecord[] }) {
  const t = useTranslations("training.records");
  const fmt = useTrainingFormat();
  if (records.length === 0) return <Empty title={t("empty")}>{t("emptyHint")}</Empty>;
  const byExercise = new Map<string, CurrentRecord[]>();
  for (const r of records) byExercise.set(r.exercise_name, [...(byExercise.get(r.exercise_name) ?? []), r]);
  const th = "py-2 pr-3 text-label font-semibold uppercase tracking-[0.08em]";
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm tabular" data-testid="pr-board">
        <caption className="sr-only">{t("caption")}</caption>
        <thead className="text-muted">
          <tr>
            <th scope="col" className={th}>{t("exercise")}</th>
            <th scope="col" className={th}>{t("record")}</th>
            <th scope="col" className={`${th} text-right`}>{t("value")}</th>
            <th scope="col" className={`${th} pr-0 text-right`}>{t("when")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {[...byExercise.entries()].map(([name, list]) =>
            list.map((r, i) => (
              <tr key={`${r.exercise_id}-${r.kind}-${r.reps ?? ""}`} data-exercise={r.exercise_id} data-kind={r.kind} data-value={r.value} data-reps={r.reps ?? ""}>
                <th scope="row" className="py-2 pr-3 font-semibold">
                  {i === 0 ? (
                    <Link href={`/training/progress?exercise=${r.exercise_id}`} className="hover:text-accent-ink">
                      {name}
                    </Link>
                  ) : (
                    <span className="sr-only">{name}</span>
                  )}
                </th>
                <td className="py-2 pr-3 text-muted">{fmt.kind(r.kind)}</td>
                <td className="py-2 pr-3 text-right font-bold">{fmt.record(r)}</td>
                <td className="py-2 text-right text-xs text-muted">
                  <Link href={`/training/history/${r.workout_id}`} className="hover:text-accent-ink">
                    {fmt.date(r.achieved_at)}
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
