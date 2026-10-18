# Connecting the real Strava account (P7.7)

The production backend needs its own Strava API application, a public callback (Tailscale
Funnel, P7.3) and one webhook subscription. These steps are done once by the owner; each one has
a row in [operations.md → Owner checks](operations.md#owner-checks) where its output is recorded.

## 1. Create the API application
1. Open <https://www.strava.com/settings/api> (logged in as the athlete whose data you sync).
2. Fill in: Application Name `trainsync`, Category "Data Importer", Website your GitHub repo URL.
3. **Authorization Callback Domain**: the Funnel host only, without scheme or path, e.g.
   `mac.tail1234.ts.net` (from `scripts/funnel.sh status`). Strava then accepts any redirect URI on
   that host; the backend uses `$PUBLIC_API_BASE_URL/auth/strava/callback`.
4. Copy **Client ID** and **Client Secret** into `.env.prod`:
   ```
   STRAVA_CLIENT_ID=…
   STRAVA_CLIENT_SECRET=…
   ```
   and pick a random `STRAVA_WEBHOOK_VERIFY_TOKEN`
   (`python -c "import secrets; print(secrets.token_urlsafe(24))"`).
5. `scripts/mac-prod.sh up` so the containers pick up the new values (a `restart` would not).

Strava's API agreement allows a personal application to read your own data; the app starts in
the default "single player" mode (only the owner can connect), which is all trainsync needs.

## 2. Connect the account and backfill
1. Open `$PUBLIC_API_BASE_URL/auth/strava/login` in the browser, or the dashboard's
   Sync → "Connect Strava" (P7.6). Approve `read,activity:read_all`.
2. The callback stores the encrypted tokens and queues the backfill. Watch it:
   ```
   curl -s -H "X-API-Key: <one of API_KEYS>" "$PUBLIC_API_BASE_URL/v1/sync/status" | python -m json.tool
   ```
   `rate_limit.short_ratio` shows how much of the 15-minute budget is used; the backfill pauses
   itself above 80 % (ADR 0004) and continues in the next window, so a long history can take a
   few hours. Nothing needs to be done while it waits.

## 3. Subscribe to webhooks
Strava sends new, changed and deleted activities to one callback per application. Creating the
subscription makes Strava call `GET $PUBLIC_API_BASE_URL/webhooks/strava?hub.challenge=…` first,
so the stack must be up and Funnel on.
```
uv run python scripts/strava-subscription.py create      # prints STRAVA_WEBHOOK_SUBSCRIPTION_ID=…
# put that line into .env.prod, then:
scripts/mac-prod.sh up
uv run python scripts/strava-subscription.py view
```
`delete` removes it (e.g. before moving the backend to another host); `create` again afterwards.
A `400` from `create` means one already exists (`view`, `delete`) or the callback was not
reachable/verified (check Funnel and `make public-check`).

## 4. Check a real webhook
Edit the title of a recent activity on strava.com. Within a minute it shows up in
`/v1/activities` (and in the bot's new-activity notification for a new upload).
