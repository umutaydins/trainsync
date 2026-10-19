"use client";

import { Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, Failure } from "@/components/ui/states";
import { isBackendDown } from "@/features/shell/components/load-failed";
import type { LogEntry } from "@/features/nutrition/types";
import { MEALS } from "@/features/nutrition/types";
import { useNutritionFormat } from "@/features/nutrition/use-nutrition-format";
import { del } from "@/lib/mutate";

const UNKNOWN = "?";

/** The day's entries grouped by meal, each removable. */
export function MealList({ entries }: { entries: LogEntry[] }) {
  const t = useTranslations("nutrition");
  const states = useTranslations("common.states");
  const fmt = useNutritionFormat();
  const router = useRouter();
  const [failed, setFailed] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const macro = (v: number | null) => (v === null ? UNKNOWN : fmt.grams(v));

  async function remove(entry: LogEntry) {
    setBusy(entry.client_id);
    setFailed(null);
    const result = await del(`/v1/nutrition/log/${entry.client_id}`);
    setBusy(null);
    if (!result.ok) return setFailed(result.status);
    router.refresh();
  }

  return (
    <Card aria-labelledby="meals-title">
      <CardHeader>
        <CardTitle id="meals-title">{t("log.title")}</CardTitle>
      </CardHeader>
      {failed !== null ? <Failure title={t("log.removeFailed")} message={isBackendDown(failed) ? states("backendDown") : undefined} /> : null}
      {entries.length === 0 ? (
        <Empty title={t("log.empty")}>{t("log.emptyHint")}</Empty>
      ) : (
        <div className="flex flex-col gap-5" data-testid="meal-list">
          {MEALS.map((meal) => {
            const items = entries.filter((e) => e.meal === meal);
            if (items.length === 0) return null;
            const total = items.reduce((sum, e) => sum + e.kcal, 0);
            return (
              <section key={meal} aria-label={t(`meals.${meal}`)}>
                <h3 className="flex justify-between text-lg font-bold">
                  <span>{t(`meals.${meal}`)}</span>
                  <span className="tabular text-muted">{fmt.kcal(total)}</span>
                </h3>
                <ul className="mt-1 divide-y divide-border">
                  {items.map((e) => (
                    <li key={e.client_id} className="flex items-center justify-between gap-3 py-2" data-testid="log-entry" data-kcal={e.kcal}>
                      <div className="min-w-0">
                        <p className="truncate font-medium">
                          {e.food_name}
                          {e.brand ? <span className="font-normal text-muted"> · {e.brand}</span> : null}
                        </p>
                        <p className="text-xs text-muted tabular">
                          {fmt.grams(e.grams)} · {fmt.kcal(e.kcal)} · {t("log.macros", { protein: macro(e.protein_g), carbs: macro(e.carbs_g), fat: macro(e.fat_g) })}
                        </p>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => void remove(e)}
                        disabled={busy === e.client_id}
                        aria-label={t("log.removeLabel", { food: e.food_name, meal: t(`mealIn.${meal}`) })}
                      >
                        <Trash2 aria-hidden />
                      </Button>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </Card>
  );
}
