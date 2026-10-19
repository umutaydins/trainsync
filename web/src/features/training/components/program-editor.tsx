"use client";

import { ArrowDown, ArrowUp, Plus, X } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ExercisePicker } from "@/features/training/components/exercise-picker";
import { type DraftDay, type DraftExercise, type DraftProgram, move, newExercise } from "@/features/training/program-draft";
import type { Exercise } from "@/features/training/types";

/** The preview or a saved program, edited in place: names, weeks, exercises per day and their numbers. */
export function ProgramEditor({
  draft,
  minutes,
  exercises,
  onChange,
  onSave,
  onCancel,
  saving,
}: {
  draft: DraftProgram;
  minutes: number[] | null;
  exercises: Exercise[];
  onChange: (draft: DraftProgram) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const t = useTranslations("training.programs.editor");
  const [picking, setPicking] = useState<string | null>(null);
  const setDay = (key: string, change: (day: DraftDay) => DraftDay) =>
    onChange({ ...draft, days: draft.days.map((d) => (d.key === key ? change(d) : d)) });

  return (
    <Card aria-labelledby="editor-title">
      <CardHeader>
        <CardTitle id="editor-title">{draft.id ? t("editTitle") : t("previewTitle")}</CardTitle>
      </CardHeader>
      <div className="flex flex-col gap-5" data-testid="program-editor">
        <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
          <Field label={t("name")}>
            <Input value={draft.name} onChange={(e) => onChange({ ...draft, name: e.target.value })} />
          </Field>
          <Field label={t("weeks")}>
            <Input inputMode="numeric" value={draft.weeks} onChange={(e) => onChange({ ...draft, weeks: e.target.value })} />
          </Field>
        </div>
        {draft.days.map((day, d) => (
          <fieldset key={day.key} className="min-w-0 rounded-card border border-border p-3" data-testid="editor-day">
            <legend className="px-1 font-bold">
              {t("day", { index: d + 1 })}
              {minutes?.[d] !== undefined ? <span className="font-normal text-muted"> · {t("about", { minutes: Math.round(minutes[d] ?? 0) })}</span> : null}
            </legend>
            <Field label={t("dayName")}>
              <Input value={day.name} onChange={(e) => setDay(day.key, (x) => ({ ...x, name: e.target.value }))} />
            </Field>
            <ol className="mt-3 flex flex-col gap-2">
              {day.exercises.map((e, i) => (
                <ExerciseRow
                  key={e.key}
                  exercise={e}
                  first={i === 0}
                  last={i === day.exercises.length - 1}
                  onChange={(change) => setDay(day.key, (x) => ({ ...x, exercises: x.exercises.map((y) => (y.key === e.key ? { ...y, ...change } : y)) }))}
                  onMove={(delta) => setDay(day.key, (x) => ({ ...x, exercises: move(x.exercises, i, delta) }))}
                  onRemove={() => setDay(day.key, (x) => ({ ...x, exercises: x.exercises.filter((y) => y.key !== e.key) }))}
                />
              ))}
            </ol>
            {picking === day.key ? (
              <div className="mt-3 rounded-card border border-border p-3">
                <ExercisePicker
                  exercises={exercises}
                  onCancel={() => setPicking(null)}
                  onPick={(exercise) => {
                    setDay(day.key, (x) => ({ ...x, exercises: [...x.exercises, newExercise(exercise)] }));
                    setPicking(null);
                  }}
                />
              </div>
            ) : (
              <Button variant="ghost" className="mt-2 text-accent-ink" onClick={() => setPicking(day.key)}>
                <Plus aria-hidden />
                {t("addTo", { day: day.name || t("day", { index: d + 1 }) })}
              </Button>
            )}
          </fieldset>
        ))}
        <div className="flex flex-wrap gap-2">
          <Button size="lg" onClick={onSave} disabled={saving}>
            {saving ? t("saving") : draft.id ? t("saveChanges") : t("save")}
          </Button>
          <Button size="lg" variant="secondary" onClick={onCancel}>
            {draft.id ? t("cancel") : t("discard")}
          </Button>
        </div>
      </div>
    </Card>
  );
}

type NumberField = "sets" | "repMin" | "repMax" | "restSeconds" | "startWeightKg";
const FIELDS: readonly { name: NumberField; key: string; mode: "numeric" | "decimal" }[] = [
  { name: "sets", key: "sets", mode: "numeric" },
  { name: "repMin", key: "repMin", mode: "numeric" },
  { name: "repMax", key: "repMax", mode: "numeric" },
  { name: "restSeconds", key: "rest", mode: "numeric" },
  { name: "startWeightKg", key: "startKg", mode: "decimal" },
];

function ExerciseRow({
  exercise,
  first,
  last,
  onChange,
  onMove,
  onRemove,
}: {
  exercise: DraftExercise;
  first: boolean;
  last: boolean;
  onChange: (change: Partial<DraftExercise>) => void;
  onMove: (delta: number) => void;
  onRemove: () => void;
}) {
  const t = useTranslations("training.programs.editor");
  const names = { name: exercise.name };
  return (
    <li className="rounded-control bg-surface-2 p-2.5" data-testid="editor-exercise">
      <div className="flex items-center justify-between gap-2">
        <p className="min-w-0 truncate font-semibold">{exercise.name}</p>
        <div className="flex shrink-0 gap-1">
          <Button variant="ghost" size="icon" onClick={() => onMove(-1)} disabled={first} aria-label={t("up", names)}>
            <ArrowUp aria-hidden />
          </Button>
          <Button variant="ghost" size="icon" onClick={() => onMove(1)} disabled={last} aria-label={t("down", names)}>
            <ArrowDown aria-hidden />
          </Button>
          <Button variant="ghost" size="icon" onClick={onRemove} aria-label={t("remove", names)}>
            <X aria-hidden />
          </Button>
        </div>
      </div>
      <div className="mt-2 grid grid-cols-5 gap-1.5">
        {FIELDS.map((field) => (
          <label key={field.name} className="block min-w-0 text-xs text-muted">
            <span className="block truncate">{t(field.key)}</span>
            <input
              inputMode={field.mode}
              value={exercise[field.name]}
              onChange={(e) => onChange({ [field.name]: e.target.value })}
              aria-label={t("fieldLabel", { field: t(field.key), name: exercise.name })}
              className="mt-0.5 h-touch w-full min-w-0 rounded-control border border-border bg-surface px-1 text-center text-sm text-text tabular outline-none focus:border-accent focus:ring-2 focus:ring-accent/40"
            />
          </label>
        ))}
      </div>
    </li>
  );
}
