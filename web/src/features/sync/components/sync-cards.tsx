import { Link2 } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useId, type ReactNode } from "react";

import { Badge, type Tone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty } from "@/components/ui/states";
import { cn } from "@/lib/cn";
import type { BreakerState, SyncRun, SyncStatus } from "@/lib/types";

/** The BFF asks the API for the authorize URL as this user; the API sends the browser back to /sync. */
export const STRAVA_CONNECT_URL = "/api/strava/connect";

type SyncErrorCode = NonNullable<SyncRun["error_code"]>;
/** Errors the person can fix themselves: Strava wants a fresh authorization. */
const RECONNECT: ReadonlySet<SyncErrorCode> = new Set(["strava_auth", "deauthorized"]);

const RUN_TONES: Record<string, Tone> = { succeeded: "ok", running: "accent", paused: "warn", failed: "bad" };
const BREAKER_TONES: Record<BreakerState, Tone> = { closed: "ok", half_open: "warn", open: "bad" };
const WARN_RATIO = 0.8;
const BAD_RATIO = 0.95;
const PERCENT = 100;

function useSyncFormat() {
  const format = useFormatter();
  return {
    count: (n: number) => format.number(n),
    dateTime: (iso: string) => format.dateTime(new Date(iso), { dateStyle: "medium", timeStyle: "short" }),
  };
}

function Block({ id, title, action, children }: { id: string; title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <Card aria-labelledby={id}>
      <CardHeader>
        <CardTitle id={id}>{title}</CardTitle>
        {action}
      </CardHeader>
      {children}
    </Card>
  );
}

export function SyncRuns({ status, isOwner = false }: { status: SyncStatus; isOwner?: boolean }) {
  const t = useTranslations("sync");
  if (status.athletes.length === 0) {
    return (
      <Block id="runs-title" title={t("runs.title")}>
        <Empty title={t("noStrava")}>{t("noStravaHint")}</Empty>
      </Block>
    );
  }
  return (
    <Block id="runs-title" title={t("runs.title")}>
      <div className="flex flex-col gap-5">
        {status.athletes.map((athlete) => (
          <div key={athlete.athlete_id}>
            <p className="mb-2 text-xs font-medium text-muted">{t("runs.athlete", { id: athlete.strava_athlete_id })}</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <RunCard kind="backfill" run={athlete.backfill} isOwner={isOwner} />
              <RunCard kind="incremental" run={athlete.incremental} isOwner={isOwner} />
            </div>
          </div>
        ))}
      </div>
    </Block>
  );
}

function RunCard({ kind, run, isOwner }: { kind: "backfill" | "incremental"; run: SyncRun | null; isOwner: boolean }) {
  const t = useTranslations("sync.runs");
  const fmt = useSyncFormat();
  const status = run ? (t.has(`status.${run.status}`) ? t(`status.${run.status}`) : run.status) : null;
  return (
    <div className="rounded-card border border-border bg-surface-2/40 p-4" data-testid={`run-${kind}`} data-status={run?.status ?? "none"}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-bold">{t(kind)}</h3>
        {run ? <Badge tone={RUN_TONES[run.status] ?? "neutral"}>{status}</Badge> : <Badge>{t("never")}</Badge>}
      </div>
      {run ? (
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted">{t("pages")}</dt>
          <dd className="text-right tabular">{fmt.count(run.pages)}</dd>
          <dt className="text-muted">{t("upserted")}</dt>
          <dd className="text-right tabular">{fmt.count(run.upserted)}</dd>
          <dt className="text-muted">{t("started")}</dt>
          <dd className="text-right tabular">{fmt.dateTime(run.started_at)}</dd>
          <dt className="text-muted">{run.finished_at ? t("finished") : t("lastProgress")}</dt>
          <dd className="text-right tabular">{fmt.dateTime(run.finished_at ?? run.updated_at)}</dd>
        </dl>
      ) : null}
      {run?.error_code ? <RunError code={run.error_code} detail={isOwner ? run.error : null} /> : null}
    </div>
  );
}

/**
 * Why a run failed, in words, with what to do about it. Never the raw exception: that is technical
 * detail, folded away and only for the owner.
 */
function RunError({ code, detail }: { code: SyncErrorCode; detail: string | null }) {
  const t = useTranslations("sync.errors");
  const known = t.has(`${code}.title`) ? code : "internal";
  return (
    <div className="mt-3 flex flex-col gap-2 rounded-control border border-bad/30 bg-bad-soft p-3 text-sm" data-testid="run-error" data-code={code}>
      <p className="font-semibold text-bad">{t(`${known}.title`)}</p>
      <p className="text-text">{t(`${known}.body`)}</p>
      {RECONNECT.has(code) ? (
        <Button asChild size="sm" className="self-start">
          <a href={STRAVA_CONNECT_URL}>
            <Link2 aria-hidden />
            {t("reconnect")}
          </a>
        </Button>
      ) : null}
      {detail ? (
        <details className="text-xs text-muted" data-testid="run-error-detail">
          <summary className="cursor-pointer select-none font-medium">{t("details")}</summary>
          <p className="mt-1 break-words font-mono">{detail}</p>
        </details>
      ) : null}
    </div>
  );
}

export function Webhooks({ status }: { status: SyncStatus }) {
  const t = useTranslations("sync.webhooks");
  const fmt = useSyncFormat();
  const w = status.webhooks;
  const rows: [string, number, Tone][] = [
    [t("pending"), w.pending, "neutral"],
    [t("processing"), w.processing, "neutral"],
    [t("failed"), w.failed, w.failed > 0 ? "warn" : "neutral"],
    [t("dead"), w.dead_letters, w.dead_letters > 0 ? "bad" : "neutral"],
  ];
  return (
    <Block id="webhooks-title" title={t("title")}>
      <dl className="flex flex-col gap-2 text-sm">
        {rows.map(([label, value, tone]) => (
          <div key={label} className="flex items-center justify-between">
            <dt className="text-muted">{label}</dt>
            <dd>{tone === "neutral" ? <span className="tabular">{fmt.count(value)}</span> : <Badge tone={tone}>{fmt.count(value)}</Badge>}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-xs text-muted">{w.last_received_at ? t("lastReceived", { time: fmt.dateTime(w.last_received_at) }) : t("never")}</p>
    </Block>
  );
}

function UsageBar({ label, ratio }: { label: string; ratio: number }) {
  const id = useId();
  const percent = Math.round(Math.min(Math.max(ratio, 0), 1) * PERCENT);
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <span className="text-muted" id={id}>
          {label}
        </span>
        <span className="tabular">{percent}%</span>
      </div>
      <div role="progressbar" aria-labelledby={id} aria-valuemin={0} aria-valuemax={PERCENT} aria-valuenow={percent} className="h-2 rounded-full bg-surface-3">
        <div className={cn("h-full rounded-full", ratio >= BAD_RATIO ? "bg-bad" : ratio >= WARN_RATIO ? "bg-warn" : "bg-ok")} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

export function RateLimits({ status }: { status: SyncStatus }) {
  const t = useTranslations("sync.rate");
  const fmt = useSyncFormat();
  const rate = status.rate_limit;
  return (
    <Block id="rate-title" title={t("title")}>
      {rate ? (
        <div className="flex flex-col gap-4">
          <UsageBar label={t("short")} ratio={rate.short_ratio} />
          <UsageBar label={t("daily")} ratio={rate.daily_ratio} />
          {rate.blocked_until ? (
            <p className="text-xs text-bad">{t("blocked", { time: fmt.dateTime(rate.blocked_until) })}</p>
          ) : (
            <p className="text-xs text-muted">{t("pauses")}</p>
          )}
        </div>
      ) : (
        <Empty title={t("empty")}>{t("emptyHint")}</Empty>
      )}
    </Block>
  );
}

export function Circuit({ status }: { status: SyncStatus }) {
  const t = useTranslations("sync.circuit");
  const { circuit } = status;
  return (
    <Block id="circuit-title" title={t("title")} action={<Badge tone={BREAKER_TONES[circuit.state]}>{t(`states.${circuit.state}`)}</Badge>}>
      {circuit.processes.length === 0 ? (
        <p className="text-sm text-muted">{t("none")}</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {circuit.processes.map((p) => (
            <li key={p.process} className="flex items-center justify-between gap-2">
              <span className="truncate text-muted" title={p.process}>
                {p.process}
              </span>
              <Badge tone={BREAKER_TONES[p.state]}>{t(`states.${p.state}`)}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Block>
  );
}
