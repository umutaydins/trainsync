"use client";

import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import type { FormEvent, Ref } from "react";

import { Button } from "@/components/ui/button";
import { Stepper } from "@/features/training/components/stepper";
import type { Food } from "@/features/nutrition/types";
import { scaled } from "@/features/nutrition/types";
import { useNutritionFormat } from "@/features/nutrition/use-nutrition-format";

export const GRAMS = { min: 0, max: 5000, step: 10, grid: 1, initial: "100" } as const;

export function readGrams(amount: string): number {
  return Number(amount.replace(",", "."));
}

/** How much of the picked food: a grams stepper, kcal and macros as you type, add to the meal. */
export function AmountForm({
  food,
  amount,
  onAmount,
  mealName,
  busy,
  onSubmit,
  onCancel,
  inputRef,
}: {
  food: Food;
  amount: string;
  onAmount: (amount: string) => void;
  mealName: string;
  busy: boolean;
  onSubmit: () => void;
  onCancel: () => void;
  inputRef?: Ref<HTMLInputElement>;
}) {
  const t = useTranslations("nutrition.add");
  const common = useTranslations("common.actions");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit();
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-3 rounded-card border border-accent/40 bg-surface-2/40 p-3" aria-label={t("amount")}>
      <p className="font-bold">{food.name}</p>
      <Stepper
        label={t("amount")}
        value={amount}
        onChange={onAmount}
        step={GRAMS.step}
        min={GRAMS.min}
        max={GRAMS.max}
        grid={GRAMS.grid}
        inputMode="decimal"
        inputLabel={t("grams")}
        decreaseLabel={t("fewerGrams")}
        increaseLabel={t("moreGrams")}
        inputRef={inputRef}
      />
      <LivePreview food={food} amount={amount} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" size="lg" disabled={busy}>
          <Plus aria-hidden />
          {t("addTo", { meal: mealName })}
        </Button>
        <Button type="button" size="lg" variant="secondary" onClick={onCancel}>
          {common("cancel")}
        </Button>
      </div>
    </form>
  );
}

function LivePreview({ food, amount }: { food: Food; amount: string }) {
  const t = useTranslations("nutrition.add");
  const fmt = useNutritionFormat();
  const g = readGrams(amount);
  if (!Number.isFinite(g) || g <= 0) return <p className="text-xs text-muted">{t("previewEmpty")}</p>;
  const value = (per100: number | null) => {
    const v = scaled(per100, g);
    return v === null ? t("unknown") : fmt.grams(v);
  };
  return (
    <p className="text-sm tabular" aria-live="polite" data-testid="live-preview">
      {t("preview", { kcal: fmt.kcal(scaled(food.kcal_100g, g) ?? 0), protein: value(food.protein_100g), carbs: value(food.carbs_100g), fat: value(food.fat_100g) })}
    </p>
  );
}
