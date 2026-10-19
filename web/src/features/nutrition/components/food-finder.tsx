"use client";

import { Barcode, Search, Star } from "lucide-react";
import { useTranslations } from "next-intl";
import { type Ref, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Failure } from "@/components/ui/states";
import { isBackendDown } from "@/features/shell/components/load-failed";
import type { Food, FoodList, FoodLookup } from "@/features/nutrition/types";
import { useNutritionFormat } from "@/features/nutrition/use-nutrition-format";
import { bffGet } from "@/lib/bff-get";

const BARCODE = /^\d{8,14}$/;
const LOCAL_LIMIT = 20;
const REMOTE_MIN_CHARS = 2;

type Results = { title: string; foods: Food[]; note?: string | null };

/**
 * Finds a food: favourites and recent ones first, then a search of saved foods, Open Food Facts or a
 * barcode. Native controls only, so the whole flow works with the keyboard.
 */
export function FoodFinder({
  favorites,
  recent,
  selectedId,
  onPick,
  searchRef,
}: {
  favorites: Food[];
  recent: Food[];
  selectedId: number | null;
  onPick: (food: Food) => void;
  searchRef?: Ref<HTMLInputElement>;
}) {
  const t = useTranslations("nutrition.add");
  const states = useTranslations("common.states");
  const fmt = useNutritionFormat();
  const [query, setQuery] = useState("");
  const [barcode, setBarcode] = useState("");
  const [results, setResults] = useState<Results | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<number | null>(null);
  const [barcodeInvalid, setBarcodeInvalid] = useState(false);

  async function search(kind: "local" | "remote" | "barcode") {
    setFailed(null);
    setBusy(true);
    const q = query.trim();
    const code = barcode.trim();
    const result =
      kind === "local"
        ? await bffGet<FoodList>("/v1/nutrition/foods", { q, limit: LOCAL_LIMIT })
        : await bffGet<FoodLookup>("/v1/nutrition/foods/lookup", kind === "remote" ? { q } : { barcode: code });
    setBusy(false);
    if (!result.ok || !result.data) return setFailed(result.status);
    const note = "remote" in result.data ? (result.data as FoodLookup).remote : null;
    const title = kind === "barcode" ? t("barcodeTitle", { code }) : kind === "remote" ? t("remoteTitle", { query: q }) : t("localTitle", { query: q });
    setResults({ title, foods: result.data.items, note: note === "not_found" || note === "unavailable" || note === "disabled" ? t(`remoteNotes.${note}`) : null });
  }

  const lists: Results[] = results ? [results] : [
    { title: t("favourites"), foods: favorites },
    { title: t("recent"), foods: recent },
  ];

  return (
    <div className="flex flex-col gap-4">
      <form
        className="flex flex-col gap-2"
        role="search"
        aria-label={t("searchLabel")}
        onSubmit={(e) => {
          e.preventDefault();
          if (query.trim()) void search("local");
        }}
      >
        <div className="flex items-end gap-2">
          <Field label={t("search")} className="min-w-0 flex-1">
            <Input ref={searchRef} type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("placeholder")} />
          </Field>
          <Button type="submit" variant="secondary" disabled={busy || !query.trim()}>
            <Search aria-hidden />
            {t("searchButton")}
          </Button>
        </div>
        <Button
          type="button"
          variant="ghost"
          className="self-start text-accent-ink"
          disabled={busy || query.trim().length < REMOTE_MIN_CHARS}
          onClick={() => void search("remote")}
        >
          {t("remote")}
        </Button>
      </form>

      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          const valid = BARCODE.test(barcode.trim());
          setBarcodeInvalid(!valid);
          if (valid) void search("barcode");
        }}
      >
        <Field label={t("barcode")} error={barcodeInvalid ? t("barcodeError") : undefined} className="min-w-0 flex-1">
          <Input inputMode="numeric" autoComplete="off" value={barcode} onChange={(e) => setBarcode(e.target.value)} placeholder={t("barcodePlaceholder")} />
        </Field>
        <Button type="submit" variant="secondary" disabled={busy || !barcode.trim()}>
          <Barcode aria-hidden />
          {t("lookup")}
        </Button>
      </form>

      {failed !== null ? <Failure title={t("failed")} message={isBackendDown(failed) ? states("backendDown") : t("refused")} /> : null}

      {lists.map((list) => (
        <div key={list.title}>
          <div className="flex min-h-touch items-center justify-between gap-2">
            <h3 className="text-label font-semibold uppercase tracking-[0.08em] text-muted">{list.title}</h3>
            {results ? (
              <Button variant="ghost" size="sm" onClick={() => setResults(null)}>
                {t("clear")}
              </Button>
            ) : null}
          </div>
          {list.note ? <p className="text-xs text-muted">{list.note}</p> : null}
          {list.foods.length === 0 ? (
            <p className="py-2 text-sm text-muted">{t("noFoods")}</p>
          ) : (
            <ul className="divide-y divide-border" aria-label={list.title}>
              {list.foods.map((food) => (
                <li key={food.id}>
                  <button
                    type="button"
                    onClick={() => onPick(food)}
                    aria-pressed={selectedId === food.id}
                    className="flex min-h-12 w-full items-center justify-between gap-3 rounded-control px-2 py-2 text-left text-sm hover:bg-surface-2 aria-pressed:bg-accent-soft"
                  >
                    <span className="flex min-w-0 items-center gap-1.5">
                      {food.favorite ? <Star aria-hidden className="size-3.5 shrink-0 fill-current text-accent-ink" /> : null}
                      <span className="truncate font-medium">
                        {food.name}
                        {food.brand ? <span className="font-normal text-muted"> · {food.brand}</span> : null}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs text-muted tabular">{t("per100", { kcal: fmt.kcal(food.kcal_100g) })}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}
