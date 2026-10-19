"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Card, ErrorState, buttonClass, inputClass, secondaryButtonClass } from "@/components/ui";
import { put } from "@/lib/mutate";
import type { ActivityBaseline, Profile, ProfileIn } from "@/features/nutrition/types";
import { kcal } from "@/features/nutrition/types";

const BASELINES: { value: ActivityBaseline; text: string }[] = [
  { value: "sedentary", text: "Sedentary (mostly sitting)" },
  { value: "light", text: "Light (on your feet some of the day)" },
  { value: "moderate", text: "Moderate (on your feet most of the day)" },
];

function optionalInt(value: string): number | null | "bad" {
  if (value.trim() === "") return null;
  const n = Number(value);
  return Number.isInteger(n) ? n : "bad";
}

/**
 * Profile and targets (PUT /v1/nutrition/profile) and today's body weight. A target below the
 * estimated basal rate is saved as entered; the API's note is shown as information.
 */
export function ProfileForm({ profile, date }: { profile: Profile | null; date: string }) {
  const router = useRouter();
  const [values, setValues] = useState({
    sex: profile?.sex ?? "male",
    birthYear: profile ? String(profile.birth_year) : "",
    height: profile ? String(profile.height_cm) : "",
    baseline: profile?.activity_baseline ?? "light",
    kcalTarget: profile?.kcal_target != null ? String(profile.kcal_target) : "",
    proteinTarget: profile?.protein_target_g != null ? String(profile.protein_target_g) : "",
  });
  const [weight, setWeight] = useState(profile?.weight_kg != null ? String(profile.weight_kg) : "");
  const [note, setNote] = useState<string | null>(profile?.warning ?? null);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const birthYear = Number(values.birthYear);
    const height = Number(values.height.replace(",", "."));
    const kcalTarget = optionalInt(values.kcalTarget);
    const proteinTarget = optionalInt(values.proteinTarget);
    if (!Number.isInteger(birthYear) || birthYear < 1900 || birthYear > 2100) return setError("Birth year: 1900 to 2100");
    if (!Number.isFinite(height) || height < 100 || height > 250) return setError("Height: 100 to 250 cm");
    if (kcalTarget === "bad" || (kcalTarget !== null && (kcalTarget < 1 || kcalTarget > 10000))) return setError("kcal target: 1 to 10000, or empty");
    if (proteinTarget === "bad" || (proteinTarget !== null && (proteinTarget < 0 || proteinTarget > 1000))) {
      return setError("Protein target: 0 to 1000 g, or empty");
    }
    const body: ProfileIn = {
      sex: values.sex,
      birth_year: birthYear,
      height_cm: height,
      activity_baseline: values.baseline,
      kcal_target: kcalTarget,
      protein_target_g: proteinTarget,
    };
    setBusy(true);
    setError(null);
    setSaved(null);
    const result = await put<Profile>("/v1/nutrition/profile", body);
    setBusy(false);
    if (!result.ok || !result.data) return setError(result.ok ? "Empty answer" : result.error);
    setNote(result.data.warning);
    setSaved(
      result.data.bmr_kcal === null ? "Profile saved." : `Profile saved. Estimated basal rate today: ${kcal(result.data.bmr_kcal)}.`,
    );
    router.refresh();
  }

  async function saveWeight(event: React.FormEvent) {
    event.preventDefault();
    const kg = Number(weight.replace(",", "."));
    if (!Number.isFinite(kg) || kg <= 0 || kg >= 500) return setError("Body weight: more than 0, below 500 kg");
    setBusy(true);
    setError(null);
    const result = await put(`/v1/training/body-metrics/${date}`, { weight_kg: Math.round(kg * 100) / 100 });
    setBusy(false);
    if (!result.ok) return setError(result.error);
    setSaved(`Body weight for ${date} saved.`);
    router.refresh();
  }

  const set = (key: keyof typeof values) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setValues((v) => ({ ...v, [key]: e.target.value }));

  return (
    <Card title="Profile and targets" labelledBy="profile-title">
      <form onSubmit={(e) => void save(e)} className="space-y-3" aria-labelledby="profile-title">
        <p className="text-xs text-muted">Used only for the basal-rate estimate (Mifflin–St Jeor). Targets are optional.</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="block text-sm font-medium">
            Sex (for the equation)
            <select value={values.sex} onChange={set("sex")} className={`${inputClass} mt-1 min-h-11`}>
              <option value="male">Male</option>
              <option value="female">Female</option>
            </select>
          </label>
          <label className="block text-sm font-medium">
            Birth year
            <input inputMode="numeric" value={values.birthYear} onChange={set("birthYear")} className={`${inputClass} mt-1 min-h-11`} />
          </label>
          <label className="block text-sm font-medium">
            Height (cm)
            <input inputMode="decimal" value={values.height} onChange={set("height")} className={`${inputClass} mt-1 min-h-11`} />
          </label>
        </div>
        <label className="block text-sm font-medium">
          Everyday activity (outside logged exercise)
          <select value={values.baseline} onChange={set("baseline")} className={`${inputClass} mt-1 min-h-11`}>
            {BASELINES.map((b) => (
              <option key={b.value} value={b.value}>
                {b.text}
              </option>
            ))}
          </select>
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm font-medium">
            kcal target (optional)
            <input inputMode="numeric" value={values.kcalTarget} onChange={set("kcalTarget")} className={`${inputClass} mt-1 min-h-11`} />
          </label>
          <label className="block text-sm font-medium">
            Protein target in g (optional)
            <input inputMode="numeric" value={values.proteinTarget} onChange={set("proteinTarget")} className={`${inputClass} mt-1 min-h-11`} />
          </label>
        </div>
        <button type="submit" className={`${buttonClass} min-h-11`} disabled={busy}>
          Save profile
        </button>
      </form>

      <form onSubmit={(e) => void saveWeight(e)} className="mt-5 flex items-end gap-2 border-t border-border pt-4">
        <label className="block flex-1 text-sm font-medium">
          Body weight on {date} (kg)
          <input inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} className={`${inputClass} mt-1 min-h-11`} />
        </label>
        <button type="submit" className={`${secondaryButtonClass} min-h-11`} disabled={busy}>
          Save weight
        </button>
      </form>

      {note ? (
        <p role="note" className="mt-4 rounded-xl border border-border bg-surface-2 px-4 py-3 text-sm" data-testid="profile-note">
          <span className="font-medium">Note: </span>
          {note}
        </p>
      ) : null}
      {error ? (
        <div className="mt-4">
          <ErrorState title="Not saved" message={error} />
        </div>
      ) : null}
      <p role="status" className="mt-2 text-sm text-ok">
        {saved}
      </p>
    </Card>
  );
}
