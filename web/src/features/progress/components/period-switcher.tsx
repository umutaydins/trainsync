"use client";

import { CalendarRange } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { type FormEvent, useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Segmented } from "@/components/ui/segmented";
import { ResponsiveSheet } from "@/components/ui/sheet";
import { cn } from "@/lib/cn";
import type { Period, PeriodQuery, RangeError } from "@/features/progress/types";
import { PERIOD_TABS, progressHref, rangeError } from "@/features/progress/types";

type Choice = (typeof PERIOD_TABS)[number] | "custom";

/**
 * The sticky W / M / 3M / 6M / Y / All switcher and the custom range sheet. The period lives in
 * the URL, so a view can be shared and the server renders it; the lift and year choices stay.
 */
export function PeriodSwitcher({ query, today }: { query: PeriodQuery; today: string }) {
  const t = useTranslations("progress.period");
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [open, setOpen] = useState(false);

  const go = (next: Pick<PeriodQuery, "period" | "from" | "to">) => {
    startTransition(() => router.push(progressHref({ ...query, ...next }), { scroll: false }));
  };
  const choices: Choice[] = [...PERIOD_TABS, "custom"];
  // Custom is a calendar icon on phones (its name stays spoken), so all seven fit from 360 px.
  const options = choices.map((value) => ({
    value,
    label: t(`short.${value}`),
    ariaLabel: t(`long.${value}`),
    ...(value === "custom" ? { icon: CalendarRange, iconOnPhone: true } : {}),
  }));
  const current: Choice = isChoice(query.period) ? query.period : "custom";

  return (
    <div
      className={cn(
        "sticky top-0 z-20 -mx-4 bg-bg/90 px-4 pb-3 pt-[max(0.5rem,env(safe-area-inset-top))] backdrop-blur sm:-mx-6 sm:px-6",
        pending && "animate-pulse",
      )}
      aria-busy={pending}
      data-testid="period-switcher"
    >
      <Segmented
        value={current}
        options={options}
        label={t("label")}
        onChange={(value) => (value === "custom" ? setOpen(true) : go({ period: value }))}
      />
      {current === "custom" ? (
        <Button variant="ghost" size="sm" className="mt-1" onClick={() => setOpen(true)}>
          <CalendarRange aria-hidden />
          {t("editRange")}
        </Button>
      ) : null}
      <ResponsiveSheet open={open} onOpenChange={setOpen} title={t("customTitle")} description={t("customHint")} closeLabel={t("close")}>
        <CustomRange
          initial={query.period === "custom" ? query : undefined}
          today={today}
          onApply={(from, to) => {
            setOpen(false);
            go({ period: "custom", from, to });
          }}
        />
      </ResponsiveSheet>
    </div>
  );
}

function isChoice(period: Period): period is Choice {
  return period === "custom" || (PERIOD_TABS as readonly Period[]).includes(period);
}

/** Two dates; `from` after `to` or a missing date keeps the sheet open with the reason. */
export function CustomRange({
  initial,
  today,
  onApply,
}: {
  initial?: Pick<PeriodQuery, "from" | "to">;
  today: string;
  onApply: (from: string, to: string) => void;
}) {
  const t = useTranslations("progress.period");
  const [from, setFrom] = useState(initial?.from ?? "");
  const [to, setTo] = useState(initial?.to ?? today);
  const [error, setError] = useState<RangeError | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const problem = rangeError(from, to);
    setError(problem);
    if (problem === null) onApply(from, to);
  };

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4 pb-2">
      <div className="grid grid-cols-2 gap-3">
        <Field label={t("from")}>
          <Input type="date" value={from} max={today} onChange={(e) => setFrom(e.target.value)} />
        </Field>
        <Field label={t("to")} error={error ? t(`errors.${error}`) : undefined}>
          <Input type="date" value={to} max={today} onChange={(e) => setTo(e.target.value)} />
        </Field>
      </div>
      <Button type="submit" size="lg" block>
        <CalendarRange aria-hidden />
        {t("apply")}
      </Button>
    </form>
  );
}
