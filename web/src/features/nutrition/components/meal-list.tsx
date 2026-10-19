"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Card, EmptyState, ErrorState } from "@/components/ui";
import { del } from "@/lib/mutate";
import type { LogEntry } from "@/features/nutrition/types";
import { MEALS, grams, kcal } from "@/features/nutrition/types";
import { label } from "@/features/training/types";

function macros(e: LogEntry): string {
  const part = (name: string, v: number | null) => `${name} ${v === null ? "?" : grams(v)}`;
  return [part("P", e.protein_g), part("C", e.carbs_g), part("F", e.fat_g)].join(" · ");
}

/** The day's entries by meal, each removable. */
export function MealList({ entries }: { entries: LogEntry[] }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function remove(entry: LogEntry) {
    setBusy(entry.client_id);
    setError(null);
    const result = await del(`/v1/nutrition/log/${entry.client_id}`);
    setBusy(null);
    if (!result.ok) return setError(result.error);
    router.refresh();
  }

  return (
    <Card title="Meals" labelledBy="meals-title">
      {error ? <ErrorState title="Could not remove the entry" message={error} /> : null}
      {entries.length === 0 ? (
        <EmptyState title="Nothing logged for this day">Add a food below.</EmptyState>
      ) : (
        <div className="space-y-4" data-testid="meal-list">
          {MEALS.map((meal) => {
            const items = entries.filter((e) => e.meal === meal);
            if (items.length === 0) return null;
            const total = items.reduce((sum, e) => sum + e.kcal, 0);
            return (
              <section key={meal} aria-label={label(meal)}>
                <h3 className="flex justify-between text-xs font-semibold uppercase tracking-wide text-muted">
                  <span>{label(meal)}</span>
                  <span className="tabular-nums">{kcal(total)}</span>
                </h3>
                <ul className="mt-1 divide-y divide-border">
                  {items.map((e) => (
                    <li key={e.client_id} className="flex items-center justify-between gap-3 py-2" data-testid="log-entry" data-kcal={e.kcal}>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {e.food_name}
                          {e.brand ? <span className="font-normal text-muted"> · {e.brand}</span> : null}
                        </p>
                        <p className="text-xs text-muted tabular-nums">
                          {grams(e.grams)} · {kcal(e.kcal)} · {macros(e)}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => void remove(e)}
                        disabled={busy === e.client_id}
                        aria-label={`Remove ${e.food_name} from ${meal}`}
                        className="min-h-11 shrink-0 rounded-lg px-3 text-sm text-muted hover:bg-surface-2 hover:text-text"
                      >
                        Remove
                      </button>
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
