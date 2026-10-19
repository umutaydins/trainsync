"use client";

import { useId, useState } from "react";

import { inputClass, secondaryButtonClass } from "@/components/ui";
import type { Exercise } from "@/features/training/types";
import { label } from "@/features/training/types";

const MAX_RESULTS = 12;

/** Filters the exercise library (already loaded) by name, muscle or equipment. */
export function ExercisePicker({
  exercises,
  onPick,
  onCancel,
}: {
  exercises: Exercise[];
  onPick: (exercise: Exercise) => void;
  onCancel: () => void;
}) {
  const [query, setQuery] = useState("");
  const inputId = useId();
  const q = query.trim().toLowerCase();
  const matches = (q
    ? exercises.filter((e) => `${e.name} ${e.primary_muscle} ${e.equipment}`.toLowerCase().includes(q))
    : exercises
  ).slice(0, MAX_RESULTS);

  return (
    <div className="rounded-2xl border border-border bg-surface p-4">
      <label htmlFor={inputId} className="mb-1 block text-sm font-medium">
        Find an exercise
      </label>
      <input
        id={inputId}
        type="search"
        autoFocus
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Name, muscle or equipment"
        className={inputClass}
      />
      <ul className="mt-2 max-h-72 divide-y divide-border overflow-y-auto" aria-label="Exercises">
        {matches.map((e) => (
          <li key={e.id}>
            <button
              type="button"
              onClick={() => onPick(e)}
              className="flex min-h-11 w-full items-center justify-between gap-2 px-1 py-2 text-left text-sm hover:bg-surface-2"
            >
              <span>{e.name}</span>
              <span className="text-xs text-muted">
                {label(e.primary_muscle)} · {e.equipment}
              </span>
            </button>
          </li>
        ))}
        {matches.length === 0 ? <li className="py-3 text-sm text-muted">No exercise matches “{query}”.</li> : null}
      </ul>
      <button type="button" className={`${secondaryButtonClass} mt-2`} onClick={onCancel}>
        Cancel
      </button>
    </div>
  );
}
