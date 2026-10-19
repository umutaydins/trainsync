import { Card } from "@/components/ui";
import { formatDay } from "@/lib/format";
import type { DaySummary, RangeSummary } from "@/features/nutrition/types";
import { ESTIMATE_GAP_TEXT, grams, kcal } from "@/features/nutrition/types";

/*
 * Nutrition copy is neutral on purpose: numbers, targets and what is unknown, never a verdict
 * (tests/nutrition-copy.test.tsx scans every visible string for judgement words).
 */

const RING = 34;
const CIRC = 2 * Math.PI * RING;

function Ring({
  label,
  value,
  target,
  unit,
  format,
}: {
  label: string;
  value: number;
  target: number | null;
  unit: string;
  format: (v: number) => string;
}) {
  const share = target && target > 0 ? Math.min(1, value / target) : 0;
  return (
    <div className="flex flex-col items-center text-center" data-testid={`ring-${unit}`} data-value={value} data-target={target ?? ""}>
      <svg viewBox="0 0 80 80" className="size-20" aria-hidden="true">
        <circle cx="40" cy="40" r={RING} fill="none" stroke="var(--surface-2)" strokeWidth="8" />
        {target ? (
          <circle
            cx="40"
            cy="40"
            r={RING}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={`${share * CIRC} ${CIRC}`}
            transform="rotate(-90 40 40)"
          />
        ) : null}
      </svg>
      <p className="mt-1 text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="text-sm font-semibold tabular-nums">{format(value)}</p>
      <p className="text-xs text-muted">{target ? `of ${format(target)}` : "no target set"}</p>
    </div>
  );
}

/** kcal and protein against the targets; carbs and fat as amounts (there are no targets for them). */
export function DailyRings({ summary }: { summary: DaySummary }) {
  const left = summary.kcal_remaining;
  return (
    <Card title="Today’s totals" labelledBy="totals-title">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Ring label="Energy" unit="kcal" value={summary.intake_kcal} target={summary.kcal_target} format={kcal} />
        <Ring label="Protein" unit="protein" value={summary.protein_g} target={summary.protein_target_g} format={grams} />
        <Ring label="Carbs" unit="carbs" value={summary.carbs_g} target={null} format={grams} />
        <Ring label="Fat" unit="fat" value={summary.fat_g} target={null} format={grams} />
      </div>
      <div className="mt-4 space-y-1 text-sm text-muted">
        <p data-testid="intake-kcal" data-value={summary.intake_kcal}>
          {kcal(summary.intake_kcal)} from {summary.entry_count} {summary.entry_count === 1 ? "entry" : "entries"}
          {left === null ? "" : left >= 0 ? ` · ${kcal(left)} to the target` : ` · ${kcal(-left)} above the target`}
        </p>
        {summary.macros_complete ? null : <p>Some foods have no macro data; the macro totals leave them out.</p>}
      </div>
    </Card>
  );
}

function Row({ label, value, note, testId }: { label: string; value: string; note?: string; testId: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2" data-testid={testId}>
      <dt className="text-sm">
        {label}
        {note ? <span className="block text-xs text-muted">{note}</span> : null}
      </dt>
      <dd className="text-right text-sm font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

const UNKNOWN = "unknown";

/**
 * Intake against an *estimated* expenditure (ADR 0019). Every estimate says so; anything the API
 * could not compute, or computed without some activities' energy, shows as "unknown", never a guess.
 */
export function EnergyBalanceCard({ summary }: { summary: DaySummary }) {
  const exerciseNote =
    summary.exercise_unknown_count > 0
      ? `${summary.exercise_unknown_count} ${summary.exercise_unknown_count === 1 ? "activity has" : "activities have"} no energy data`
      : summary.activities.length === 0
        ? "no synced activities"
        : `${summary.activities.length} ${summary.activities.length === 1 ? "activity" : "activities"} from Strava`;
  const expenditureKnown = summary.expenditure_kcal !== null && summary.exercise_complete;
  const balanceKnown = summary.balance_kcal !== null && summary.balance_complete;
  const balance = summary.balance_kcal ?? 0;
  return (
    <Card title="Energy balance (estimate)" labelledBy="balance-title">
      <dl className="divide-y divide-border" data-testid="energy-balance">
        <Row testId="row-intake" label="Intake" note="logged food" value={kcal(summary.intake_kcal)} />
        <Row
          testId="row-bmr"
          label="Basal rate"
          note="estimate, Mifflin–St Jeor"
          value={summary.bmr_kcal === null ? UNKNOWN : kcal(summary.bmr_kcal)}
        />
        <Row
          testId="row-baseline"
          label="Everyday activity"
          note={`estimate${summary.activity_baseline ? `, ${summary.activity_baseline}` : ""}, exercise not included`}
          value={summary.baseline_kcal === null ? UNKNOWN : kcal(summary.baseline_kcal)}
        />
        <Row
          testId="row-exercise"
          label="Exercise"
          note={exerciseNote}
          value={summary.exercise_complete ? kcal(summary.exercise_kcal) : `${kcal(summary.exercise_kcal)} + unknown`}
        />
        <Row testId="row-expenditure" label="Expenditure" note="estimate" value={expenditureKnown ? kcal(summary.expenditure_kcal ?? 0) : UNKNOWN} />
        <Row
          testId="row-balance"
          label="Balance"
          note="estimate, intake minus expenditure"
          value={balanceKnown ? `${balance > 0 ? "+" : balance < 0 ? "−" : ""}${kcal(Math.abs(balance))}` : UNKNOWN}
        />
      </dl>
      {summary.estimate_unavailable_reason ? (
        <p className="mt-3 text-xs text-muted">{ESTIMATE_GAP_TEXT[summary.estimate_unavailable_reason]}</p>
      ) : null}
      {!summary.exercise_complete ? (
        <p className="mt-3 text-xs text-muted">
          Strava has no energy figure for some activities, so expenditure and balance are shown as unknown rather than guessed.
        </p>
      ) : null}
    </Card>
  );
}

/** Week averages over the days with logged food, and the days themselves. */
export function WeeklyAverages({ weekly }: { weekly: RangeSummary }) {
  const logged = weekly.days.filter((d) => d.entry_count > 0);
  const avgProtein = logged.length ? logged.reduce((sum, d) => sum + d.protein_g, 0) / logged.length : null;
  const t = weekly.totals;
  return (
    <Card title="This week" labelledBy="week-title">
      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4" data-testid="week-totals">
        <div>
          <dt className="text-xs text-muted">Average intake</dt>
          <dd className="font-semibold tabular-nums">{t.avg_intake_kcal === null ? "—" : kcal(t.avg_intake_kcal)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Average protein</dt>
          <dd className="font-semibold tabular-nums">{avgProtein === null ? "—" : grams(avgProtein)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Days logged</dt>
          <dd className="font-semibold tabular-nums">
            {t.days_logged} of {weekly.days.length}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Balance (estimate)</dt>
          <dd className="font-semibold tabular-nums">
            {t.balance_kcal === null || !t.balance_complete ? "unknown" : `${t.balance_kcal > 0 ? "+" : t.balance_kcal < 0 ? "−" : ""}${kcal(Math.abs(t.balance_kcal))}`}
          </dd>
        </div>
      </dl>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-left text-xs tabular-nums" data-testid="week-table">
          <caption className="sr-only">Daily intake this week</caption>
          <thead className="text-muted">
            <tr>
              <th scope="col" className="py-1.5 pr-3 font-medium">Day</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">Intake</th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium">Protein</th>
              <th scope="col" className="py-1.5 text-right font-medium">Exercise</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {weekly.days.map((d) => (
              <tr key={d.date} data-day={d.date} data-intake={d.intake_kcal}>
                <th scope="row" className="py-1.5 pr-3 font-normal">{formatDay(d.date)}</th>
                <td className="py-1.5 pr-3 text-right">{d.entry_count ? kcal(d.intake_kcal) : "—"}</td>
                <td className="py-1.5 pr-3 text-right">{d.entry_count ? grams(d.protein_g) : "—"}</td>
                <td className="py-1.5 text-right">{d.exercise_complete ? kcal(d.exercise_kcal) : `${kcal(d.exercise_kcal)} + unknown`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
