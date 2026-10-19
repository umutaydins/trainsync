"use client";

import { Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ResponsiveSheet } from "@/components/ui/sheet";
import type { Exercise } from "@/features/training/types";

const MAX_RESULTS = 12;

/** Filters the exercise library (already loaded) by name, muscle or equipment, in either language. */
export function ExercisePicker({
  exercises,
  onPick,
  onCancel,
}: {
  exercises: Exercise[];
  onPick: (exercise: Exercise) => void;
  onCancel?: () => void;
}) {
  const t = useTranslations("training.picker");
  const muscles = useTranslations("progress.strength.muscles");
  const equipment = useTranslations("training.equipment");
  const common = useTranslations("common.actions");
  const [query, setQuery] = useState("");
  const q = query.trim().toLocaleLowerCase();
  const describe = (e: Exercise) => `${muscles(e.primary_muscle)} · ${equipment(e.equipment)}`;
  const matches = (q
    ? exercises.filter((e) => `${e.name} ${e.primary_muscle} ${e.equipment} ${describe(e)}`.toLocaleLowerCase().includes(q))
    : exercises
  ).slice(0, MAX_RESULTS);

  return (
    <div className="flex flex-col gap-3">
      <Field label={t("find")}>
        <Input type="search" autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("placeholder")} />
      </Field>
      <ul className="max-h-80 divide-y divide-border overflow-y-auto" aria-label={t("list")}>
        {matches.map((e) => (
          <li key={e.id}>
            <button
              type="button"
              onClick={() => onPick(e)}
              className="flex min-h-touch w-full items-center justify-between gap-3 rounded-control px-2 py-2 text-left text-sm hover:bg-surface-2"
            >
              <span className="font-medium">{e.name}</span>
              <span className="shrink-0 text-xs text-muted">{describe(e)}</span>
            </button>
          </li>
        ))}
        {matches.length === 0 ? (
          <li className="flex items-center gap-2 py-3 text-sm text-muted">
            <Search aria-hidden className="size-4" />
            {t("none", { query })}
          </li>
        ) : null}
      </ul>
      {onCancel ? (
        <Button variant="secondary" className="self-start" onClick={onCancel}>
          {common("cancel")}
        </Button>
      ) : null}
    </div>
  );
}

/** The picker in a bottom sheet (the workout screen). */
export function ExercisePickerSheet({
  open,
  onOpenChange,
  exercises,
  onPick,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  exercises: Exercise[];
  onPick: (exercise: Exercise) => void;
}) {
  const t = useTranslations("training.picker");
  const common = useTranslations("common.actions");
  return (
    <ResponsiveSheet open={open} onOpenChange={onOpenChange} title={t("title")} closeLabel={common("close")}>
      <ExercisePicker exercises={exercises} onPick={onPick} />
    </ResponsiveSheet>
  );
}
