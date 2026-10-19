# 0027 — Uptime check from GitHub Actions, stack alerts from the worker

- Status: accepted
- Date: 2026-10-18

## Context
The backend runs on one MacBook (ADR 0023) behind Tailscale Funnel (ADR 0025). The failures that
matter most — the Mac is off or asleep, Funnel is down, Docker stopped — silence everything on
the Mac, including any alert it could send. Other failures happen inside a running stack and are
invisible from outside: the Strava circuit breaker stuck open, webhook events dead-lettered,
backups no longer written, syncing stopped. Telegram is already the owner's channel (bot,
notifications, backup alerts). Alerts must not spam: one message when something breaks, one when
it is fixed, nothing for a one-off blip.

## Decision
Two independent mechanisms, both ending in a Telegram message:

1. **External uptime** — `.github/workflows/uptime.yml`, every 15 minutes, `GET /health/ready` on
   `UPTIME_URL` (real) and `UPTIME_DEMO_URL` (demo). A pure state machine
   (`src/trainsync/ops/uptime.py`, per target `up → failing(n) → down`) sends "down" at the second
   consecutive failure, nothing while it stays down, "recovered" once when it answers again; a
   single failure followed by a success sends nothing. Standard library only, run with the
   runner's `python3`; Telegram via `trainsync.ops.alert` with the token in the environment.
   **State** is a small JSON file in the Actions cache: restored from the newest entry with the
   prefix `uptime-state-`, saved under a new key (`uptime-state-<run id>-<attempt>`) every run.
2. **Stack alerts** — an arq cron in the worker every 5 minutes (`src/trainsync/modules/notifications/alerts.py`)
   with four conditions: circuit not closed for 30 min, dead letters > 0, newest backup older
   than 36 h, no successful sync for 2 h while an athlete is connected. Each condition alerts once
   when it starts and once when it clears. **State** is one Redis key per condition,
   `alert:<condition>` = `{"bad_since", "alerted"}`, without expiry; production Redis runs with
   `appendonly yes`, so worker restarts and reboots keep it. The worker reads backup ages from the
   backup folder, bind-mounted **read-only** at `/backups` (`BACKUP_DIR`); backup names carry
   their UTC time, so only the file names are listed. Thresholds are settings (`ALERT_*`); alerts
   are off while no Telegram target is configured.

## Alternatives considered
- Uptime state in a GitHub issue or a state branch — durable, but needs `issues: write` or
  `contents: write` on a schedule-triggered workflow, and every run becomes a visible repo write.
  The cache needs no extra permission; losing it (7 days unused, or eviction) costs at most one
  repeated "down" message, which is acceptable.
- Failing the workflow run while a target is down — GitHub e-mails on every failed scheduled run,
  i.e. every 15 minutes. The run is red only when Telegram could not be told.
- A hosted uptime service (UptimeRobot, Better Stack) — one more account and provider; GitHub
  Actions already runs our scheduled public check (P7.3). Schedules can be delayed by several
  minutes under load, which is fine for a 15-minute check.
- Stack alert state in the `notifications` table with new kinds — needs a migration and an enum
  change for ephemeral state; claim/release fits "send once ever" (new activity, check-in), not
  "start / clear, again and again". Redis already holds the breaker and rate-limit state.
- The backup service writing its last success to Redis — the backup image has no Redis client and
  only reaches Postgres; the backup files are the ground truth anyway (a "success" marker with no
  file behind it would be worse).
- Alerting from Prometheus/Alertmanager — not deployed on the Mac (ADR 0010 keeps metrics for
  scraping), and it would add two services for four conditions.

## Consequences
- An outage of the whole Mac is reported within about 15–30 minutes (two runs), from outside.
- GitHub runs schedules only from the default branch: the uptime check starts after the Phase 7
  merge. Scheduled workflows in a repository without activity for 60 days are disabled by GitHub.
- The circuit condition treats "no breaker report" (the open key expired between probes) as
  unknown and keeps its timer; only an explicit closed report clears it.
- Wiping Redis forgets which stack alerts were sent: a still-active condition alerts once more,
  and a recovery that happens meanwhile is not announced.
- The worker container gains a read-only view of the encrypted backups (it cannot decrypt them).
