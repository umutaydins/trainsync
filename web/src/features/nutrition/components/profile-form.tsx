"use client";

import { Info } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Failure } from "@/components/ui/states";
import { isBackendDown } from "@/features/shell/components/load-failed";
import { ProfileFields } from "@/features/nutrition/components/profile-fields";
import { type ProfileField, profileValues, toProfile } from "@/features/nutrition/profile";
import type { Profile } from "@/features/nutrition/types";
import { useNutritionFormat } from "@/features/nutrition/use-nutrition-format";
import { put } from "@/lib/mutate";

const WEIGHT_MAX_KG = 500;
const CENTS = 100;

type Problem = "weightError" | { status: number };

/**
 * Profile and targets (`PUT /v1/nutrition/profile`, the same fields as the onboarding) and the
 * day's body weight. A target below the estimated basal rate is saved as entered; the page says so
 * as information, in the user's language.
 */
export function ProfileForm({ profile, date }: { profile: Profile | null; date: string }) {
  const t = useTranslations("nutrition.profile");
  const states = useTranslations("common.states");
  const fmt = useNutritionFormat();
  const router = useRouter();
  const [values, setValues] = useState(() => profileValues(profile));
  const [invalid, setInvalid] = useState<ProfileField | null>(null);
  const [weight, setWeight] = useState(profile?.weight_kg != null ? String(profile.weight_kg) : "");
  const [belowBmr, setBelowBmr] = useState<number | null>(profile?.warning ? (profile.bmr_kcal ?? null) : null);
  const [hasNote, setHasNote] = useState(Boolean(profile?.warning));
  const [saved, setSaved] = useState<string | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [busy, setBusy] = useState(false);
  const dayText = fmt.day(date);

  async function save(event: FormEvent) {
    event.preventDefault();
    const checked = toProfile(values);
    if (!checked.ok) return setInvalid(checked.field);
    setInvalid(null);
    setBusy(true);
    setProblem(null);
    setSaved(null);
    const result = await put<Profile>("/v1/nutrition/profile", checked.body);
    setBusy(false);
    if (!result.ok || !result.data) return setProblem({ status: result.status });
    setHasNote(Boolean(result.data.warning));
    setBelowBmr(result.data.bmr_kcal);
    setSaved(result.data.bmr_kcal === null ? t("saved") : t("savedWithBmr", { bmr: fmt.kcal(result.data.bmr_kcal) }));
    router.refresh();
  }

  async function saveWeight(event: FormEvent) {
    event.preventDefault();
    const kg = Number(weight.replace(",", "."));
    if (!Number.isFinite(kg) || kg <= 0 || kg >= WEIGHT_MAX_KG) return setProblem("weightError");
    setBusy(true);
    setProblem(null);
    const result = await put(`/v1/training/body-metrics/${date}`, { weight_kg: Math.round(kg * CENTS) / CENTS });
    setBusy(false);
    if (!result.ok) return setProblem({ status: result.status });
    setSaved(t("weightSaved", { date: dayText }));
    router.refresh();
  }

  return (
    <Card aria-labelledby="profile-title">
      <form onSubmit={(e) => void save(e)} className="flex flex-col gap-4" aria-labelledby="profile-title">
        <div>
          <h2 id="profile-title" className="text-lg font-bold tracking-tight">
            {t("title")}
          </h2>
          <p className="mt-1 text-sm text-muted">{t("body")}</p>
        </div>
        <ProfileFields values={values} invalid={invalid} onChange={setValues} />
        <Button type="submit" className="self-start" disabled={busy}>
          {t("save")}
        </Button>
      </form>

      <form onSubmit={(e) => void saveWeight(e)} className="mt-5 flex items-end gap-2 border-t border-border pt-4">
        <Field label={t("weight", { date: dayText })} className="min-w-0 flex-1">
          <Input inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} />
        </Field>
        <Button type="submit" variant="secondary" disabled={busy}>
          {t("saveWeight")}
        </Button>
      </form>

      {hasNote ? (
        <p role="note" className="mt-4 flex gap-2 rounded-control border border-border bg-surface-2 p-3 text-sm" data-testid="profile-note">
          <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-accent-ink" />
          <span>
            <span className="font-semibold">{t("note")}: </span>
            {t("belowBmr", { bmr: belowBmr === null ? "—" : fmt.kcal(belowBmr) })}
          </span>
        </p>
      ) : null}
      {problem ? (
        <div className="mt-4">
          <Failure
            title={t("notSaved")}
            message={typeof problem === "string" ? t(problem) : isBackendDown(problem.status) ? states("backendDown") : undefined}
          />
        </div>
      ) : null}
      <p role="status" className="mt-2 text-sm font-medium text-ok">
        {saved}
      </p>
    </Card>
  );
}
