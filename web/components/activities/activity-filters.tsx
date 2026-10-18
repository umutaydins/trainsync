import Link from "next/link";

import { buttonClass, inputClass, secondaryButtonClass } from "@/components/ui";
import type { ActivityFilters } from "@/lib/activities-query";
import { sportLabel } from "@/lib/format";

/** Plain GET form: filters end up in the URL and work without JavaScript. */
export function ActivityFiltersForm({ filters, sports }: { filters: ActivityFilters; sports: string[] }) {
  return (
    <form
      method="get"
      action="/activities"
      aria-label="Filter activities"
      className="mb-4 flex flex-wrap items-end gap-3 rounded-2xl border border-border bg-surface p-3"
    >
      <div>
        <label htmlFor="filter-from" className="mb-1 block text-xs font-medium text-muted">From</label>
        <input id="filter-from" name="from" type="date" defaultValue={filters.from} className={`${inputClass} py-1.5`} />
      </div>
      <div>
        <label htmlFor="filter-to" className="mb-1 block text-xs font-medium text-muted">To</label>
        <input id="filter-to" name="to" type="date" defaultValue={filters.to} className={`${inputClass} py-1.5`} />
      </div>
      <div>
        <label htmlFor="filter-sport" className="mb-1 block text-xs font-medium text-muted">Sport</label>
        <select id="filter-sport" name="sport_type" defaultValue={filters.sport_type ?? ""} className={`${inputClass} py-1.5 sm:w-40`}>
          <option value="">All sports</option>
          {sports.map((sport) => (
            <option key={sport} value={sport}>{sportLabel(sport)}</option>
          ))}
        </select>
      </div>
      <div className="flex gap-2">
        <button type="submit" className={`${buttonClass} py-1.5`}>Apply</button>
        <Link href="/activities" className={`${secondaryButtonClass} py-1.5`}>Clear</Link>
      </div>
    </form>
  );
}
