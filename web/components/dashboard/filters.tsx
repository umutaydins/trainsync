"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { buttonClass, inputClass } from "@/components/ui";
import { sportLabel } from "@/lib/format";
import { PRESETS, rangeHref, type DashboardRange } from "@/lib/range";

/** Range presets (links), custom from/to, and a sport filter. All state lives in the URL. */
export function DashboardFilters({ range, sports }: { range: DashboardRange; sports: string[] }) {
  const router = useRouter();
  const [from, setFrom] = useState(range.from);
  const [to, setTo] = useState(range.to);

  function applyCustom(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (from && to && from <= to) router.push(rangeHref(range, { preset: "custom", from, to }));
  }

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-border bg-surface p-3 lg:flex-row lg:items-center lg:justify-between">
      <nav aria-label="Date range" className="flex flex-wrap gap-1">
        {PRESETS.map((preset) => (
          <Link
            key={preset.id}
            href={rangeHref(range, { preset: preset.id })}
            aria-current={range.preset === preset.id ? "true" : undefined}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              range.preset === preset.id ? "bg-accent text-accent-contrast" : "text-muted hover:bg-surface-2 hover:text-text"
            }`}
          >
            {preset.label}
          </Link>
        ))}
      </nav>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <form onSubmit={applyCustom} className="flex flex-wrap items-end gap-2" aria-label="Custom range">
          <div>
            <label htmlFor="range-from" className="mb-1 block text-xs font-medium text-muted">From</label>
            <input id="range-from" type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} className={`${inputClass} py-1.5`} />
          </div>
          <div>
            <label htmlFor="range-to" className="mb-1 block text-xs font-medium text-muted">To</label>
            <input id="range-to" type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} className={`${inputClass} py-1.5`} />
          </div>
          <button type="submit" className={`${buttonClass} py-1.5`}>Apply</button>
        </form>
        <div>
          <label htmlFor="sport" className="mb-1 block text-xs font-medium text-muted">Sport</label>
          <select
            id="sport"
            value={range.sportType ?? ""}
            onChange={(e) => router.push(rangeHref(range, { sportType: e.target.value || undefined }))}
            className={`${inputClass} py-1.5 sm:w-40`}
          >
            <option value="">All sports</option>
            {sports.map((sport) => (
              <option key={sport} value={sport}>{sportLabel(sport)}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
