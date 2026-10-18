import Link from "next/link";

import { ErrorState, StatTile } from "@/components/ui";
import { load } from "@/lib/api";
import type { CheckinSummary } from "@/lib/checkins";
import { formatAdherence, plural } from "@/lib/checkins";
import { checkinsApi } from "@/lib/checkins-api";

/** Streak and adherence (P6.9): two stat tiles. */
export function CheckinTiles({ summary }: { summary: CheckinSummary }) {
  const adherenceHint =
    summary.adherence === null
      ? "no active program"
      : `${summary.planned_days_done} of ${plural(summary.planned_days, "planned day")}`;
  return (
    <dl aria-label="Check-ins" data-testid="checkin-tiles" className="grid grid-cols-2 gap-3">
      <StatTile
        label="Check-in streak"
        value={plural(summary.current_streak, "day")}
        hint={`longest ${plural(summary.longest_streak, "day")}`}
      />
      <StatTile label="Adherence" value={formatAdherence(summary)} hint={adherenceHint} />
    </dl>
  );
}

/** Dashboard block: the last four ISO weeks, linking to the calendar. */
export async function CheckinTilesBlock() {
  const result = await load(() => checkinsApi.summary());
  if (!result.ok) return <ErrorState title="Could not load check-ins" message={result.error} />;
  return (
    <div>
      <CheckinTiles summary={result.data} />
      <Link href="/training/checkins" className="mt-1.5 inline-block text-xs font-medium text-accent hover:underline">
        Check-in calendar →
      </Link>
    </div>
  );
}
