# 0026 — Manual `make deploy` on the Mac instead of a self-hosted GitHub runner

- Status: accepted
- Date: 2026-10-18

## Context
Production runs on the owner's personal MacBook (ADR 0023). Shipping a new version means
building images, migrating the database and restarting containers on that machine. The obvious
continuous-deployment setup is a self-hosted GitHub Actions runner on the Mac that deploys every
green push to `main`. A deploy must also be reversible quickly, and some migrations cannot be
undone without losing data.

## Decision
- **No self-hosted runner.** The owner runs `make deploy` on the Mac (`scripts/deploy.sh`).
  It refuses unless the worktree is clean, the branch is `main`, `HEAD == origin/main` after a
  fetch, and the `ci` workflow run for that SHA is `completed`/`success` (`gh run list`). So
  only reviewed, CI-tested commits reach production, without CI ever running on the Mac.
- Steps: build images tagged with the SHA (12 chars) → pre-deploy backup
  (`backup now predeploy<sha7>`, ADR 0024) → record `alembic current` → migrations as the
  one-shot `migrate` container → `up -d` → smoke test through the gateway (`/health/ready`,
  `GET /v1/sync/status` with the first `API_KEYS` key, Telegram `getMe` when a bot token is
  set). A failed build, backup or migration aborts with the old containers still running; a
  failed smoke test rolls back automatically.
- State (current and previous SHA/tag, the revision to return to, the backup label) lives in
  `~/Library/Application Support/trainsync/deploy-state`; `scripts/mac-prod.sh` starts that tag
  at login, so a reboot after a rollback does not resurrect the checked-out commit. One line per
  deploy/rollback goes to `~/Library/Logs/trainsync/deploys.log`; the result goes to Telegram.
- **Rollback** (`make rollback`) brings the previous tag back, one step only. Every migration
  declares `reversible = True/False`: True means `downgrade()` restores the previous schema and
  keeps every row the previous code can read (it may drop what only the new code wrote).
  `scripts/migration_reversibility.py` lists the migrations crossed by the deploy; if all are
  reversible they are downgraded with the *new* image (only it has their downgrade code) before
  the old images start. If any is not, rollback refuses and prints the restore procedure for
  the pre-deploy backup; `rollback --restored` then starts the old images.

## Alternatives considered
- Self-hosted GitHub runner on the Mac — a runner executes workflow code from the repository
  on the owner's personal machine, with access to the home directory, the Keychain session,
  `.env.prod` and the Docker socket (root-equivalent in the VM, with every secret). Any
  compromised action, dependency or workflow change becomes code execution there. It would also
  keep an outbound long-poll and a job queue alive on a 16 GB fanless laptop, and Funnel is
  deliberately limited to the gateway (ADR 0025): nothing else on the Mac should take work
  from the internet.
- GitHub-hosted CI deploying over SSH/Tailscale — needs a Tailscale auth key and an SSH key
  with deploy rights stored in GitHub secrets: the same blast radius, one hop removed.
- Pulling images from a registry instead of building on the Mac — saves build time but adds a
  registry, credentials and multi-arch builds for a single machine.
- Automatic downgrades for every migration — some downgrades lose data the old code needs;
  making that explicit per migration is cheaper than finding out during an incident.

## Consequences
- Deploys happen only when the owner is at (or SSH'd into) the Mac; a merged PR is not live
  until `make deploy`. Acceptable for a personal service.
- `gh` must be logged in on the Mac (read access to Actions is enough).
- Every new migration must state `reversible`; the Alembic template forces the choice, a unit
  test checks it and an integration test steps every migration down and up again.
- Rollback goes back one deploy. Going further back is a manual `git switch --detach <sha>`,
  `mac-prod.sh build` and `up`, with the same migration caveats.
- Data written between a deploy and its rollback into new tables/columns is lost by the
  downgrade; the pre-deploy backup is the fallback.
