"use client";

import { useEffect, useId, useState } from "react";

import { Badge, Card, EmptyState, ErrorState, type Tone } from "@/components/ui";
import { formatCount, formatDateTime } from "@/lib/format";
import type { BreakerState, SyncRun, SyncStatus } from "@/lib/types";

export const REFRESH_MS = 15_000;

const RUN_TONES: Record<string, Tone> = { succeeded: "ok", running: "accent", paused: "warn", failed: "bad" };
const BREAKER: Record<BreakerState, { tone: Tone; label: string }> = {
  closed: { tone: "ok", label: "Closed" },
  half_open: { tone: "warn", label: "Half-open" },
  open: { tone: "bad", label: "Open" },
};

/** Sync health, refreshed from the BFF every 15 s. Keeps the last good data if a refresh fails. */
export function SyncStatusView({ initial, intervalMs = REFRESH_MS }: { initial: SyncStatus; intervalMs?: number }) {
  const [status, setStatus] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const response = await fetch("/api/ts/v1/sync/status", { cache: "no-store" });
        const body: unknown = await response.json().catch(() => null);
        if (!response.ok) throw new Error((body as { error?: string } | null)?.error || `request failed (${response.status})`);
        if (cancelled) return;
        setStatus(body as SyncStatus);
        setError(null);
        setUpdatedAt(new Date().toISOString());
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "request failed");
      }
    }, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [intervalMs]);

  return (
    <div className="space-y-4" data-testid="sync-status">
      <p className="text-xs text-muted" aria-live="polite">
        Refreshes every {Math.round(intervalMs / 1000)} s{updatedAt ? ` · updated ${formatDateTime(updatedAt)}` : ""}
      </p>
      {error ? <ErrorState title="Refresh failed, showing the last known state" message={error} /> : null}
      <SyncRuns status={status} />
      <div className="grid gap-4 md:grid-cols-3">
        <Webhooks status={status} />
        <RateLimits status={status} />
        <Circuit status={status} />
      </div>
    </div>
  );
}

function SyncRuns({ status }: { status: SyncStatus }) {
  if (status.athletes.length === 0) {
    return (
      <Card title="Sync runs" labelledBy="runs-title">
        <EmptyState title="No Strava account connected">Use “Connect Strava” to start the first backfill.</EmptyState>
      </Card>
    );
  }
  return (
    <Card title="Sync runs" labelledBy="runs-title">
      <div className="space-y-5">
        {status.athletes.map((athlete) => (
          <div key={athlete.athlete_id}>
            <p className="mb-2 text-xs font-medium text-muted">Strava athlete {athlete.strava_athlete_id}</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <RunCard kind="Backfill" run={athlete.backfill} />
              <RunCard kind="Incremental" run={athlete.incremental} />
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function RunCard({ kind, run }: { kind: string; run: SyncRun | null }) {
  return (
    <div className="rounded-xl border border-border p-4" data-testid={`run-${kind.toLowerCase()}`} data-status={run?.status ?? "none"}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{kind}</h3>
        {run ? <Badge tone={RUN_TONES[run.status] ?? "neutral"}>{run.status}</Badge> : <Badge>never ran</Badge>}
      </div>
      {run ? (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted">Pages</dt>
          <dd className="text-right tabular-nums">{formatCount(run.pages)}</dd>
          <dt className="text-muted">Upserted</dt>
          <dd className="text-right tabular-nums">{formatCount(run.upserted)}</dd>
          <dt className="text-muted">Started</dt>
          <dd className="text-right tabular-nums">{formatDateTime(run.started_at)}</dd>
          <dt className="text-muted">{run.finished_at ? "Finished" : "Last progress"}</dt>
          <dd className="text-right tabular-nums">{formatDateTime(run.finished_at ?? run.updated_at)}</dd>
        </dl>
      ) : null}
      {run?.error ? <p className="mt-3 break-words text-xs text-bad">{run.error}</p> : null}
    </div>
  );
}

function Webhooks({ status }: { status: SyncStatus }) {
  const w = status.webhooks;
  const rows: [string, number, Tone][] = [
    ["Pending", w.pending, "neutral"],
    ["Processing", w.processing, "neutral"],
    ["Failed (retrying)", w.failed, w.failed > 0 ? "warn" : "neutral"],
    ["Dead letters", w.dead_letters, w.dead_letters > 0 ? "bad" : "neutral"],
  ];
  return (
    <Card title="Webhooks" labelledBy="webhooks-title">
      <dl className="space-y-2 text-sm">
        {rows.map(([label, value, tone]) => (
          <div key={label} className="flex items-center justify-between">
            <dt className="text-muted">{label}</dt>
            <dd>
              {tone === "neutral" ? <span className="tabular-nums">{formatCount(value)}</span> : <Badge tone={tone}>{formatCount(value)}</Badge>}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-xs text-muted">
        Last received {w.last_received_at ? formatDateTime(w.last_received_at) : "never"}
      </p>
    </Card>
  );
}

function UsageBar({ label, ratio }: { label: string; ratio: number }) {
  const id = useId();
  const percent = Math.round(Math.min(Math.max(ratio, 0), 1) * 100);
  const color = ratio >= 0.95 ? "bg-bad" : ratio >= 0.8 ? "bg-warn" : "bg-ok";
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <span className="text-muted" id={id}>{label}</span>
        <span className="tabular-nums">{percent}%</span>
      </div>
      <div
        role="progressbar"
        aria-labelledby={id}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-2 rounded-full bg-surface-2"
      >
        <div className={`h-full rounded-full ${color}`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

function RateLimits({ status }: { status: SyncStatus }) {
  const rate = status.rate_limit;
  return (
    <Card title="Strava rate limit" labelledBy="rate-title">
      {rate ? (
        <div className="space-y-4">
          <UsageBar label="15 minutes" ratio={rate.short_ratio} />
          <UsageBar label="Daily" ratio={rate.daily_ratio} />
          {rate.blocked_until ? (
            <p className="text-xs text-bad">Blocked after a 429 until {formatDateTime(rate.blocked_until)}</p>
          ) : (
            <p className="text-xs text-muted">Backfill pauses above 80% of the 15-minute budget.</p>
          )}
        </div>
      ) : (
        <EmptyState title="No usage yet">Shown once Strava has answered.</EmptyState>
      )}
    </Card>
  );
}

function Circuit({ status }: { status: SyncStatus }) {
  const { circuit } = status;
  const overall = BREAKER[circuit.state];
  return (
    <Card title="Circuit breaker" labelledBy="circuit-title" action={<Badge tone={overall.tone}>{overall.label}</Badge>}>
      {circuit.processes.length === 0 ? (
        <p className="text-sm text-muted">No process has reported yet.</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {circuit.processes.map((p) => (
            <li key={p.process} className="flex items-center justify-between gap-2">
              <span className="truncate text-muted" title={p.process}>{p.process}</span>
              <Badge tone={BREAKER[p.state].tone}>{BREAKER[p.state].label}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
