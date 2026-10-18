/** `/activities` URL filters → `/v1/activities` query. Dates are inclusive UTC days in the URL. */

export interface ActivityFilters {
  from?: string;
  to?: string;
  sport_type?: string;
}

export const PAGE_SIZE = 50;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

type SearchParams = Record<string, string | string[] | undefined>;

function single(value: string | string[] | undefined): string | undefined {
  const v = Array.isArray(value) ? value[0] : value;
  return v ? v : undefined;
}

export function parseActivityFilters(params: SearchParams): ActivityFilters {
  const from = single(params.from);
  const to = single(params.to);
  return {
    from: from && DATE_RE.test(from) ? from : undefined,
    to: to && DATE_RE.test(to) ? to : undefined,
    sport_type: single(params.sport_type),
  };
}

/** The API's `to` is exclusive (`start_date < to`), so an inclusive day becomes the next midnight. */
export function toApiQuery(filters: ActivityFilters): Record<string, string> {
  const query: Record<string, string> = { limit: String(PAGE_SIZE) };
  if (filters.from) query.from = filters.from;
  if (filters.to) {
    const next = new Date(`${filters.to}T00:00:00Z`);
    next.setUTCDate(next.getUTCDate() + 1);
    query.to = next.toISOString().slice(0, 10);
  }
  if (filters.sport_type) query.sport_type = filters.sport_type;
  return query;
}
