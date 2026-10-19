"use client";

import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Failure } from "@/components/ui/states";
import { isBackendDown } from "@/features/shell/components/load-failed";
import type { Food, FoodIn } from "@/features/nutrition/types";
import { post } from "@/lib/mutate";

const KCAL_MAX = 1000;
const MACRO_MAX = 100;

type Problem = "nameError" | "kcalError" | "macroError" | { status: number };
type TextField = "name" | "brand" | "kcal" | "protein" | "carbs" | "fat";

const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));

/** A food of your own (values per 100 g) → `POST /v1/nutrition/foods`; it is picked right away. */
export function NewFoodForm({ onCreated, onCancel }: { onCreated: (food: Food) => void; onCancel: () => void }) {
  const t = useTranslations("nutrition.add.newFood");
  const add = useTranslations("nutrition.add");
  const states = useTranslations("common.states");
  const common = useTranslations("common.actions");
  const [values, setValues] = useState<Record<TextField, string>>({ name: "", brand: "", kcal: "", protein: "", carbs: "", fat: "" });
  const [favorite, setFavorite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);

  async function create(event: FormEvent) {
    event.preventDefault();
    const kcal = num(values.kcal);
    if (!values.name.trim()) return setProblem("nameError");
    if (kcal === null || !Number.isFinite(kcal) || kcal < 0 || kcal > KCAL_MAX) return setProblem("kcalError");
    const macros = [num(values.protein), num(values.carbs), num(values.fat)];
    if (macros.some((m) => m !== null && (!Number.isFinite(m) || m < 0 || m > MACRO_MAX))) return setProblem("macroError");
    const body: FoodIn = {
      name: values.name.trim(),
      brand: values.brand.trim() || null,
      kcal_100g: kcal,
      protein_100g: macros[0] ?? null,
      carbs_100g: macros[1] ?? null,
      fat_100g: macros[2] ?? null,
      favorite,
    };
    setBusy(true);
    setProblem(null);
    const result = await post<Food>("/v1/nutrition/foods", body);
    setBusy(false);
    if (!result.ok || !result.data) return setProblem({ status: result.status });
    onCreated(result.data);
  }

  const field = (key: TextField, decimal = false) => (
    <Field label={t(key)}>
      <Input inputMode={decimal ? "decimal" : undefined} value={values[key]} onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))} />
    </Field>
  );

  return (
    <form onSubmit={(e) => void create(e)} className="flex flex-col gap-3 rounded-card border border-border p-3" aria-label={t("form")}>
      <p className="font-bold">{t("title")}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {field("name")}
        {field("brand")}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {field("kcal", true)}
        {field("protein", true)}
        {field("carbs", true)}
        {field("fat", true)}
      </div>
      <label className="inline-flex min-h-touch items-center gap-3 text-sm font-medium">
        <Switch checked={favorite} onCheckedChange={setFavorite} />
        {t("favourite")}
      </label>
      {problem ? (
        <Failure
          title={t("failed")}
          message={typeof problem === "string" ? t(problem) : isBackendDown(problem.status) ? states("backendDown") : add("refused")}
        />
      ) : null}
      <div className="flex gap-2">
        <Button type="submit" disabled={busy}>
          {t("save")}
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          {common("cancel")}
        </Button>
      </div>
    </form>
  );
}
