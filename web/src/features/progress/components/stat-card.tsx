import { useLocale, useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { type Better, ChangeBadge } from "@/components/ui/change";
import { CountUp } from "@/components/ui/count-up";
import { Stat } from "@/components/ui/stat";
import { formatChangePct } from "@/features/progress/format";
import type { Change, Period } from "@/features/progress/types";
import { hasChange } from "@/features/progress/types";

const NO_VALUE = "—";

/** ▲▼ against the previous period, with a screen-reader sentence ("up 12% vs previous period"). */
export function Delta({ pct, better }: { pct: number | null; better: Better }) {
  const t = useTranslations("common.change");
  const locale = useLocale();
  if (pct == null) return null;
  const value = formatChangePct(locale, pct);
  const direction = pct > 0 ? t("up", { value }) : pct < 0 ? t("down", { value }) : t("same");
  return <ChangeBadge pct={pct} text={value} label={`${direction} ${t("vsPrevious")}`} better={better} />;
}

/**
 * One big number of a progress block: a `<dt>`/`<dd>` pair (render inside a `<dl>`), counting up
 * to its value, with its unit and its change. `text` replaces the number for clocks and paces.
 */
export function StatCard({
  label,
  value,
  text,
  digits = 0,
  unit,
  change,
  pct,
  better = "up",
  period,
  hint,
  testId,
}: {
  label: ReactNode;
  value?: number | null;
  text?: string | null;
  digits?: number;
  unit?: ReactNode;
  /** The API's change; its `change_pct` is shown unless `pct` overrides it (paces). */
  change?: Change | null;
  pct?: number | null;
  better?: Better;
  period: Period;
  hint?: ReactNode;
  testId?: string;
}) {
  const locale = useLocale();
  const shownPct = pct !== undefined ? (period === "all" ? null : pct) : hasChange(change, period) ? change.change_pct : null;
  const missing = text === null || (text === undefined && value == null);
  const shown = missing ? (
    NO_VALUE
  ) : text !== undefined ? (
    text
  ) : (
    <CountUp value={value ?? 0} locale={locale} options={{ maximumFractionDigits: digits }} />
  );
  return (
    <Stat
      label={label}
      value={shown}
      unit={missing ? undefined : unit}
      change={<Delta pct={shownPct} better={better} />}
      hint={hint}
      className="rounded-control bg-surface-2 p-3"
      data-testid={testId}
      data-value={value ?? undefined}
    />
  );
}
