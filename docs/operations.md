# Operations

## Backups and restore

Design: [ADR 0024](decisions/0024-encrypted-pg-dump-backups-with-a-restore-check.md).
The `backup` service of `compose.prod.yml` takes one encrypted `pg_dump -Fc` a day after
`BACKUP_TIME` (03:30 Europe/Istanbul by default), keeps 7 daily / 4 weekly / 6 monthly, and
after the backup on `RESTORE_CHECK_WEEKDAY` (7 = Sunday) restores it into a scratch database
and compares row counts. Failures and the weekly result go to Telegram when
`TELEGRAM_BOT_TOKEN` and a chat are set.

Files in `BACKUP_HOST_DIR` (default `~/Library/Mobile Documents/com~apple~CloudDocs/trainsync-backups`):

- `trainsync-YYYYMMDD-HHMMSS[-label].dump.age` — the dump, encrypted to `BACKUP_AGE_RECIPIENT` (UTC time).
- `trainsync-YYYYMMDD-HHMMSS[-label].counts.json` — row counts of the same snapshot.
- `.….partial` — a backup being written; never a backup, cleaned up after an hour.

### One-time setup (owner)

1. Generate the key pair (inside the backup image, nothing to install):
   ```
   mkdir -p ~/.config/trainsync && chmod 700 ~/.config/trainsync
   docker build -t trainsync-backup:keygen -f deploy/backup/Dockerfile .
   (umask 077; docker run --rm --entrypoint age-keygen trainsync-backup:keygen \
     > ~/.config/trainsync/backup-identity.txt)
   grep 'public key' ~/.config/trainsync/backup-identity.txt
   ```
2. Store the whole identity file in the password manager too. Without it no backup can be
   restored. Never put it in iCloud Drive or next to the backups.
3. In `.env.prod`: `BACKUP_AGE_RECIPIENT=age1…` (the public key) and
   `BACKUP_AGE_IDENTITY_FILE=/Users/<you>/.config/trainsync/backup-identity.txt`.
4. `mkdir -p ~/Library/Mobile\ Documents/com~apple~CloudDocs/trainsync-backups` and in Finder
   choose "Keep Downloaded" on that folder (an evicted file cannot be restore-checked).
5. Take the first backup and check it:
   ```
   make backup-now
   make restore-check
   ```

### Everyday commands

```
make backup-now                      # one backup now + retention (LABEL=predeploy to tag it)
make restore-check                   # newest backup → scratch DB → row counts vs the sidecar
scripts/restore-check.sh PATH/trainsync-….dump.age          # a specific backup
scripts/restore-check.sh --identity KEY.txt [PATH]          # with another identity file
docker compose --env-file .env.prod -f compose.prod.yml logs backup
docker compose --env-file .env.prod -f compose.prod.yml run --rm backup prune --dry-run
make restore-check-ci                # CI variant: seeded DB, throwaway key, bad backups must fail
```

### Restoring for real

1. Stop writers: `docker compose --env-file .env.prod -f compose.prod.yml stop api worker bot`.
2. Check the backup first: `scripts/restore-check.sh PATH/trainsync-….dump.age`.
3. Restore into the live database (replaces its contents):
   ```
   docker compose --env-file .env.prod -f compose.prod.yml run --rm \
     -v PATH_DIR:/restore:ro -v ~/.config/trainsync/backup-identity.txt:/run/key:ro \
     --entrypoint bash backup -c \
     'age -d -i /run/key /restore/trainsync-….dump.age | pg_restore --clean --if-exists --no-owner --no-acl -d trainsync'
   ```
4. Start again (`up -d`); migrations run forward from the restored revision (P7.5).

### Owner checks

- [ ] Key pair generated, identity in the password manager and at `BACKUP_AGE_IDENTITY_FILE`.
- [ ] `make backup-now` wrote a `.dump.age` + `.counts.json` into iCloud Drive (date, size).
- [ ] `make restore-check` passed on it (date, output line "row counts match …").
- [ ] The container can read the `chmod 600` identity file through Docker Desktop's file
      sharing (`make restore-check` would say "no age identity" otherwise).
- [ ] After the first Sunday: the weekly result arrived on Telegram.
