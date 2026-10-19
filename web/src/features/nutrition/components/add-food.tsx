"use client";

import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";

import { Card, ErrorState, buttonClass, inputClass, secondaryButtonClass } from "@/components/ui";
import { bffGet } from "@/lib/bff-get";
import { post, put } from "@/lib/mutate";
import type { Food, FoodIn, FoodList, FoodLookup, LogEntry, LogIn, Meal } from "@/features/nutrition/types";
import { MEALS, grams, kcal, scaled } from "@/features/nutrition/types";
import { label } from "@/features/training/types";

const REMOTE_TEXT: Record<FoodLookup["remote"], string | null> = {
  ok: null,
  cached: null,
  not_found: "Open Food Facts does not know this product.",
  unavailable: "Open Food Facts did not answer in time; showing saved foods only.",
  disabled: "Open Food Facts lookups are switched off; showing saved foods only.",
};

type Results = { title: string; foods: Food[]; note?: string | null };

/**
 * Add a food to the day: pick from favourites, recent or a search (saved foods, Open Food Facts,
 * barcode), or create one; enter grams and see kcal and macros as you type. Native form controls
 * only, so the whole flow works with the keyboard.
 */
export function AddFood({
  date,
  favorites,
  recent,
  newId = () => crypto.randomUUID(),
}: {
  date: string;
  favorites: Food[];
  recent: Food[];
  newId?: () => string;
}) {
  const router = useRouter();
  const [meal, setMeal] = useState<Meal>("breakfast");
  const [query, setQuery] = useState("");
  const [barcode, setBarcode] = useState("");
  const [results, setResults] = useState<Results | null>(null);
  const [selected, setSelected] = useState<{ food: Food; clientId: string } | null>(null);
  const [amount, setAmount] = useState("100");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const gramsRef = useRef<HTMLInputElement>(null);
  const ids = { meal: useId(), q: useId(), barcode: useId(), grams: useId() };

  function pick(food: Food) {
    setSelected({ food, clientId: newId() });
    setDone(null);
    setError(null);
    // Focus the grams field once it is rendered.
    setTimeout(() => gramsRef.current?.focus(), 0);
  }

  async function search(kind: "local" | "remote" | "barcode") {
    setError(null);
    setBusy(true);
    const result =
      kind === "local"
        ? await bffGet<FoodList>("/v1/nutrition/foods", { q: query.trim(), limit: 20 })
        : kind === "remote"
          ? await bffGet<FoodLookup>("/v1/nutrition/foods/lookup", { q: query.trim() })
          : await bffGet<FoodLookup>("/v1/nutrition/foods/lookup", { barcode: barcode.trim() });
    setBusy(false);
    if (!result.ok || !result.data) return setError(result.ok ? "Empty answer" : result.error);
    const note = "remote" in result.data ? REMOTE_TEXT[(result.data as FoodLookup).remote] : null;
    const title = kind === "barcode" ? `Barcode ${barcode.trim()}` : kind === "remote" ? `Open Food Facts: “${query.trim()}”` : `Saved foods: “${query.trim()}”`;
    setResults({ title, foods: result.data.items, note });
  }

  async function add(event: React.FormEvent) {
    event.preventDefault();
    if (!selected) return;
    const g = Number(amount.replace(",", "."));
    if (!Number.isFinite(g) || g <= 0 || g > 5000) return setError("Grams: more than 0, up to 5000");
    setBusy(true);
    setError(null);
    const body: LogIn = { date, meal, food_id: selected.food.id, grams: g };
    const result = await put<LogEntry>(`/v1/nutrition/log/${selected.clientId}`, body);
    setBusy(false);
    if (!result.ok) return setError(result.error);
    setDone(`Added ${grams(g)} ${selected.food.name} to ${meal}.`);
    setSelected(null);
    setAmount("100");
    router.refresh();
    searchRef.current?.focus();
  }

  const lists: Results[] = results
    ? [results]
    : [
        { title: "Favourites", foods: favorites },
        { title: "Recent", foods: recent },
      ];

  return (
    <Card title="Add food" labelledBy="add-food-title">
      <div className="space-y-4" data-testid="add-food">
        <label htmlFor={ids.meal} className="block text-sm font-medium">
          Meal
          <select id={ids.meal} value={meal} onChange={(e) => setMeal(e.target.value as Meal)} className={`${inputClass} mt-1 min-h-11`}>
            {MEALS.map((m) => (
              <option key={m} value={m}>
                {label(m)}
              </option>
            ))}
          </select>
        </label>

        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (query.trim()) void search("local");
          }}
          role="search"
          aria-label="Food search"
        >
          <label htmlFor={ids.q} className="block text-sm font-medium">
            Search foods
          </label>
          <div className="flex gap-2">
            <input
              id={ids.q}
              ref={searchRef}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. oats"
              className={`${inputClass} min-h-11 min-w-0`}
            />
            <button type="submit" className={`${secondaryButtonClass} min-h-11`} disabled={busy || !query.trim()}>
              Search
            </button>
          </div>
          <button
            type="button"
            className="min-h-11 text-sm font-medium text-accent hover:underline disabled:opacity-50"
            disabled={busy || query.trim().length < 2}
            onClick={() => void search("remote")}
          >
            Search Open Food Facts too
          </button>
        </form>

        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (/^\d{8,14}$/.test(barcode.trim())) void search("barcode");
            else setError("Barcode: 8 to 14 digits");
          }}
        >
          <label htmlFor={ids.barcode} className="block min-w-0 flex-1 text-sm font-medium">
            Barcode
            <input
              id={ids.barcode}
              inputMode="numeric"
              value={barcode}
              onChange={(e) => setBarcode(e.target.value)}
              placeholder="8 to 14 digits"
              className={`${inputClass} mt-1 min-h-11`}
            />
          </label>
          <button type="submit" className={`${secondaryButtonClass} min-h-11`} disabled={busy || !barcode.trim()}>
            Look up
          </button>
        </form>

        {lists.map((list) => (
          <div key={list.title}>
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">{list.title}</h3>
              {results ? (
                <button type="button" className="min-h-11 text-xs text-muted hover:text-text" onClick={() => setResults(null)}>
                  Clear search
                </button>
              ) : null}
            </div>
            {list.note ? <p className="text-xs text-muted">{list.note}</p> : null}
            {list.foods.length === 0 ? (
              <p className="py-2 text-sm text-muted">No foods here yet.</p>
            ) : (
              <ul className="divide-y divide-border" aria-label={list.title}>
                {list.foods.map((food) => (
                  <li key={food.id}>
                    <button
                      type="button"
                      onClick={() => pick(food)}
                      aria-pressed={selected?.food.id === food.id}
                      className="flex min-h-11 w-full items-center justify-between gap-3 py-2 text-left text-sm hover:bg-surface-2"
                    >
                      <span className="min-w-0 truncate">
                        {food.name}
                        {food.brand ? <span className="text-muted"> · {food.brand}</span> : null}
                      </span>
                      <span className="shrink-0 text-xs text-muted tabular-nums">{kcal(food.kcal_100g)} / 100 g</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}

        {selected ? (
          <form onSubmit={(e) => void add(e)} className="space-y-3 rounded-xl border border-accent/40 p-3" aria-label="Amount">
            <p className="text-sm font-medium">{selected.food.name}</p>
            <label htmlFor={ids.grams} className="block text-sm font-medium">
              Grams
              <input
                id={ids.grams}
                ref={gramsRef}
                inputMode="decimal"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className={`${inputClass} mt-1 min-h-11`}
              />
            </label>
            <LivePreview food={selected.food} amount={amount} />
            <div className="flex gap-2">
              <button type="submit" className={`${buttonClass} min-h-11`} disabled={busy}>
                Add to {meal}
              </button>
              <button type="button" className={`${secondaryButtonClass} min-h-11`} onClick={() => setSelected(null)}>
                Cancel
              </button>
            </div>
          </form>
        ) : null}

        {error ? <ErrorState title="That did not work" message={error} /> : null}
        <p role="status" className="text-sm text-ok">
          {done}
        </p>

        {creating ? (
          <NewFoodForm
            onCancel={() => setCreating(false)}
            onCreated={(food) => {
              setCreating(false);
              pick(food);
            }}
          />
        ) : (
          <button type="button" className={`${secondaryButtonClass} min-h-11`} onClick={() => setCreating(true)}>
            Create a food
          </button>
        )}
      </div>
    </Card>
  );
}

function LivePreview({ food, amount }: { food: Food; amount: string }) {
  const g = Number(amount.replace(",", "."));
  if (!Number.isFinite(g) || g <= 0) return <p className="text-xs text-muted">Enter grams to see the values.</p>;
  const v = (per100: number | null) => {
    const value = scaled(per100, g);
    return value === null ? "unknown" : grams(value);
  };
  return (
    <p className="text-sm tabular-nums" aria-live="polite" data-testid="live-preview">
      <span className="font-semibold">{kcal(scaled(food.kcal_100g, g) ?? 0)}</span> · protein {v(food.protein_100g)} · carbs {v(food.carbs_100g)} · fat{" "}
      {v(food.fat_100g)}
    </p>
  );
}

function NewFoodForm({ onCreated, onCancel }: { onCreated: (food: Food) => void; onCancel: () => void }) {
  const [values, setValues] = useState({ name: "", brand: "", kcal: "", protein: "", carbs: "", fat: "", favorite: false });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));

  async function create(event: React.FormEvent) {
    event.preventDefault();
    const kcal100 = num(values.kcal);
    if (!values.name.trim()) return setError("Name is empty");
    if (kcal100 === null || !Number.isFinite(kcal100) || kcal100 < 0 || kcal100 > 1000) return setError("kcal per 100 g: 0 to 1000");
    const macros = [num(values.protein), num(values.carbs), num(values.fat)];
    if (macros.some((m) => m !== null && (!Number.isFinite(m) || m < 0 || m > 100))) return setError("Macros per 100 g: 0 to 100, or empty if unknown");
    const body: FoodIn = {
      name: values.name.trim(),
      brand: values.brand.trim() || null,
      kcal_100g: kcal100,
      protein_100g: macros[0],
      carbs_100g: macros[1],
      fat_100g: macros[2],
      favorite: values.favorite,
    };
    setBusy(true);
    setError(null);
    const result = await post<Food>("/v1/nutrition/foods", body);
    setBusy(false);
    if (!result.ok || !result.data) return setError(result.ok ? "Empty answer" : result.error);
    onCreated(result.data);
  }

  const field = (key: "name" | "brand" | "kcal" | "protein" | "carbs" | "fat", text: string, mode?: "decimal") => (
    <label className="block text-sm font-medium">
      {text}
      <input
        inputMode={mode}
        value={values[key]}
        onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
        className={`${inputClass} mt-1 min-h-11`}
      />
    </label>
  );

  return (
    <form onSubmit={(e) => void create(e)} className="space-y-3 rounded-xl border border-border p-3" aria-label="New food">
      <p className="text-sm font-semibold">New food (values per 100 g)</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {field("name", "Name")}
        {field("brand", "Brand (optional)")}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {field("kcal", "kcal", "decimal")}
        {field("protein", "Protein g", "decimal")}
        {field("carbs", "Carbs g", "decimal")}
        {field("fat", "Fat g", "decimal")}
      </div>
      <label className="inline-flex min-h-11 items-center gap-2 text-sm">
        <input type="checkbox" checked={values.favorite} onChange={(e) => setValues((v) => ({ ...v, favorite: e.target.checked }))} />
        Add to favourites
      </label>
      {error ? <ErrorState title="Could not save the food" message={error} /> : null}
      <div className="flex gap-2">
        <button type="submit" className={`${buttonClass} min-h-11`} disabled={busy}>
          Save food
        </button>
        <button type="button" className={`${secondaryButtonClass} min-h-11`} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
