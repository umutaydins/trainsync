import { StatTile } from "@/components/ui";
import type { CheckinSummary } from "@/features/checkins/checkins";
import { formatAdherence, plural } from "@/features/checkins/checkins";

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
