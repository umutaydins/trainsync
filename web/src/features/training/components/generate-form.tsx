"use client";

import { Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { Failure } from "@/components/ui/states";
import { isBackendDown } from "@/features/shell/components/load-failed";
import type { Equipment, GenerateIn, ProgramGoal, ProgramPreview } from "@/features/training/types";
import { EQUIPMENT, GOALS } from "@/features/training/types";
import { post } from "@/lib/mutate";

const DAY_OPTIONS = [2, 3, 4, 6] as const;
const DEFAULT_DAYS = 4;
const MINUTES = { min: 20, max: 180, initial: "60" } as const;
const WEEKS = 8;

/** Days, goal, minutes and equipment → `POST /v1/training/programs/generate` → a preview to edit. */
export function GenerateForm({ onPreview }: { onPreview: (preview: ProgramPreview) => void }) {
  const t = useTranslations("training.programs.generate");
  const goals = useTranslations("training.goals");
  const equipmentName = useTranslations("training.equipment");
  const states = useTranslations("common.states");
  const [days, setDays] = useState<number>(DEFAULT_DAYS);
  const [goal, setGoal] = useState<ProgramGoal>("hypertrophy");
  const [equipment, setEquipment] = useState<Equipment[]>(["barbell", "dumbbell"]);
  const [minutes, setMinutes] = useState<string>(MINUTES.initial);
  const [busy, setBusy] = useState(false);
  const [minutesError, setMinutesError] = useState(false);
  const [failed, setFailed] = useState<number | null>(null);

  async function generate(event: FormEvent) {
    event.preventDefault();
    const session = Number(minutes);
    if (!Number.isInteger(session) || session < MINUTES.min || session > MINUTES.max) return setMinutesError(true);
    setMinutesError(false);
    setBusy(true);
    setFailed(null);
    const body: GenerateIn = { days_per_week: days, goal, equipment, session_minutes: session, weeks: WEEKS };
    const result = await post<ProgramPreview>("/v1/training/programs/generate", body);
    setBusy(false);
    if (!result.ok || !result.data) return setFailed(result.status);
    onPreview(result.data);
  }

  return (
    <Card aria-labelledby="generate-title">
      <CardHeader>
        <CardTitle id="generate-title">{t("title")}</CardTitle>
      </CardHeader>
      <form onSubmit={(e) => void generate(e)} className="flex flex-col gap-4" aria-labelledby="generate-title">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label={t("days")}>
            <Select value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {DAY_OPTIONS.map((d) => (
                <option key={d} value={d}>
                  {t("dayOption", { days: d, template: t(`templates.${d}`) })}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("goal")}>
            <Select value={goal} onChange={(e) => setGoal(e.target.value as ProgramGoal)}>
              {GOALS.map((g) => (
                <option key={g} value={g}>
                  {goals(g)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("minutes")} error={minutesError ? t("minutesError", MINUTES) : undefined}>
            <Input inputMode="numeric" value={minutes} onChange={(e) => setMinutes(e.target.value)} />
          </Field>
        </div>
        <fieldset>
          <legend className="text-sm font-medium">{t("equipment")}</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {EQUIPMENT.filter((e) => e !== "bodyweight").map((e) => (
              <label
                key={e}
                className="inline-flex h-touch cursor-pointer items-center gap-2 rounded-full border border-border px-4 text-sm font-medium has-[:checked]:border-accent has-[:checked]:bg-accent-soft has-[:checked]:text-accent-ink"
              >
                <input
                  type="checkbox"
                  className="size-4 accent-[var(--accent)]"
                  checked={equipment.includes(e)}
                  onChange={(event) => setEquipment((list) => (event.target.checked ? [...list, e] : list.filter((x) => x !== e)))}
                />
                {equipmentName(e)}
              </label>
            ))}
          </div>
        </fieldset>
        {failed !== null ? <Failure title={t("failed")} message={isBackendDown(failed) ? states("backendDown") : t("refused")} /> : null}
        <Button type="submit" size="lg" className="self-start" disabled={busy}>
          <Sparkles aria-hidden />
          {busy ? t("generating") : t("submit")}
        </Button>
      </form>
    </Card>
  );
}
