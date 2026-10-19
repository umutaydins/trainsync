"use client";

import { CheckCircle2, Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Select } from "@/components/ui/input";
import { ResponsiveSheet } from "@/components/ui/sheet";
import { Failure } from "@/components/ui/states";
import { isBackendDown } from "@/features/shell/components/load-failed";
import { AmountForm, GRAMS, readGrams } from "@/features/nutrition/components/amount-form";
import { FoodFinder } from "@/features/nutrition/components/food-finder";
import { NewFoodForm } from "@/features/nutrition/components/new-food-form";
import type { Food, LogEntry, LogIn, Meal } from "@/features/nutrition/types";
import { MEALS } from "@/features/nutrition/types";
import { useNutritionFormat } from "@/features/nutrition/use-nutrition-format";
import { put } from "@/lib/mutate";

type Problem = "gramsError" | { status: number };

/**
 * "Add food": a bottom sheet (dialog on desktop) to pick a food from favourites, recent ones or a
 * search, set the grams with a stepper and add it to a meal, or create a food. It stays open after
 * adding, so a whole meal goes in one go; the page behind refreshes.
 */
export function AddFood({
  date,
  favorites,
  recent,
  defaultMeal = "breakfast",
  newId = () => crypto.randomUUID(),
}: {
  date: string;
  favorites: Food[];
  recent: Food[];
  defaultMeal?: Meal;
  newId?: () => string;
}) {
  const t = useTranslations("nutrition");
  const states = useTranslations("common.states");
  const common = useTranslations("common.actions");
  const fmt = useNutritionFormat();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [meal, setMeal] = useState<Meal>(defaultMeal);
  const [selected, setSelected] = useState<{ food: Food; clientId: string } | null>(null);
  const [amount, setAmount] = useState<string>(GRAMS.initial);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const gramsRef = useRef<HTMLInputElement>(null);

  function pick(food: Food) {
    setSelected({ food, clientId: newId() });
    setDone(null);
    setProblem(null);
    // Focus the grams once they are rendered.
    setTimeout(() => gramsRef.current?.focus(), 0);
  }

  async function add() {
    if (!selected) return;
    const g = readGrams(amount);
    if (!Number.isFinite(g) || g <= 0 || g > GRAMS.max) return setProblem("gramsError");
    setBusy(true);
    setProblem(null);
    const body: LogIn = { date, meal, food_id: selected.food.id, grams: g };
    const result = await put<LogEntry>(`/v1/nutrition/log/${selected.clientId}`, body);
    setBusy(false);
    if (!result.ok) return setProblem({ status: result.status });
    setDone(t("add.added", { grams: fmt.grams(g), food: selected.food.name, meal: t(`mealIn.${meal}`) }));
    setSelected(null);
    setAmount(GRAMS.initial);
    router.refresh();
    searchRef.current?.focus();
  }

  return (
    <>
      <Button size="lg" block onClick={() => setOpen(true)}>
        <Plus aria-hidden />
        {t("add.open")}
      </Button>
      <ResponsiveSheet open={open} onOpenChange={setOpen} title={t("add.title")} description={t("add.description")} closeLabel={common("close")}>
        <div className="flex flex-col gap-4 pb-2" data-testid="add-food">
          <Field label={t("add.meal")}>
            <Select value={meal} onChange={(e) => setMeal(e.target.value as Meal)}>
              {MEALS.map((m) => (
                <option key={m} value={m}>
                  {t(`meals.${m}`)}
                </option>
              ))}
            </Select>
          </Field>
          <p role="status" className="flex min-h-5 items-center gap-1.5 text-sm font-medium text-ok">
            {done ? <CheckCircle2 aria-hidden className="size-4" /> : null}
            {done}
          </p>
          {selected ? (
            <AmountForm
              food={selected.food}
              amount={amount}
              onAmount={setAmount}
              mealName={t(`mealIn.${meal}`)}
              busy={busy}
              onSubmit={() => void add()}
              onCancel={() => setSelected(null)}
              inputRef={gramsRef}
            />
          ) : null}
          {problem ? (
            <Failure
              title={t("add.failed")}
              message={typeof problem === "string" ? t(`add.${problem}`) : isBackendDown(problem.status) ? states("backendDown") : t("add.refused")}
            />
          ) : null}
          <FoodFinder favorites={favorites} recent={recent} selectedId={selected?.food.id ?? null} onPick={pick} searchRef={searchRef} />
          {creating ? (
            <NewFoodForm
              onCancel={() => setCreating(false)}
              onCreated={(food) => {
                setCreating(false);
                pick(food);
              }}
            />
          ) : (
            <Button variant="outline" className="self-start" onClick={() => setCreating(true)}>
              <Plus aria-hidden />
              {t("add.create")}
            </Button>
          )}
        </div>
      </ResponsiveSheet>
    </>
  );
}
