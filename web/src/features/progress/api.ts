import "server-only";

import { cache } from "react";

import type { Bucket, Heatmap, Metric, Period, ProgressSummary, Records, Series } from "@/features/progress/types";
import { getJson } from "@/lib/api";

/**
 * Typed `/v1/stats` progress reads for server components (ADR 0038). Primitive arguments, so
 * `cache` (which compares by identity) dedupes the same call within a request.
 */
export const progressApi = {
  summary: cache((period: Period, from?: string, to?: string) =>
    getJson<ProgressSummary>("/v1/stats/summary", { period, from, to }),
  ),
  series: cache((metric: Metric, period: Period, from?: string, to?: string, bucket?: Bucket) =>
    getJson<Series>("/v1/stats/series", { metric, period, from, to, bucket }),
  ),
  heatmap: cache((year?: number) => getJson<Heatmap>("/v1/stats/heatmap", { year })),
  prs: cache((period: Period, from?: string, to?: string) => getJson<Records>("/v1/stats/prs", { period, from, to })),
};
