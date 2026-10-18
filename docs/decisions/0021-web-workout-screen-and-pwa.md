# 0021 — Web workout screen: timestamp timers, retry queue, PWA without a service worker

- Status: accepted
- Date: 2026-10-18

## Context
The active-workout screen (P6.6) runs on a phone in the gym: the screen locks between sets, the
browser freezes or throttles background tabs, the Wi-Fi drops, and people tap twice. It should
also open like an app from the home screen. Three choices needed writing down: how timers stay
right, what happens to a set that could not be sent, and how much of a PWA to build.

## Decision
- **Timers are timestamps.** The rest timer is `{endsAt, durationS, label, alerted}` and the
  workout timer is the API's `started_at`; the screen renders `endsAt − now()` (pure functions in
  `web/lib/timers.ts`, `now` injected). An interval only triggers re-renders (250 ms), and
  `visibilitychange`/`focus` re-render at once, so a locked phone or a frozen tab shows the right
  value the moment it is back. The zero alert (vibration, a short WebAudio beep, and a
  notification only if permission was already granted from a button tap) fires once; an alert
  more than 60 s late (the tab slept through zero) is skipped and the timer just shows 0:00.
- **State in localStorage per workout** (`trainsync.workout.<id>`): the rest timer and every set
  row with its client id, values, `completedAt` and status. A reload restores the timer and keeps
  the same client ids, so tapping a row again stays idempotent (ADR 0017). The screen renders on
  the client only (`next/dynamic`, `ssr: false`), since its first render depends on storage and
  the clock. Cleared when the workout is finished.
- **Set logging**: the client id is made once per row (`crypto.randomUUID`); ✓ is optimistic
  (rest timer starts at once) and sends `PUT …/sets/{client_id}`. A tap while that row's request
  is in flight is ignored. No answer (status 0), 5xx, 408 or 429 → the PUT goes into a small
  localStorage retry queue (`web/lib/retry-queue.ts`, one entry per path, newest body wins), which
  is flushed on the `online` event, after the next successful PUT, on page load and before
  finishing; a 4xx leaves the queue and shows as an error. Finishing is refused while the
  workout still has queued sets.
- **PWA, no service worker.** `app/manifest.ts` (`start_url` `/training`, `display: standalone`,
  theme `#2f6fde` from the accent token), PNG icons (192, 512, maskable 512, apple-touch 180)
  rendered from `app/icon.svg`'s shape by `web/scripts/gen-icons.mjs`, and Apple web-app meta.
  Current Chrome/Edge install without a fetch handler and iOS never needed one, so there is no
  service worker: nothing, least of all API data, is cached on the device. The manifest and icons
  are served without a session (`proxy.ts` matcher), because browsers fetch the manifest without
  cookies; they contain no data.
- **Screen Wake Lock** while the workout is open, re-requested when the page becomes visible
  again (the browser drops it on hide). Missing API or a refusal (battery saver) is not an error.

## Alternatives considered
- Counting down with `setInterval` decrements — wrong after any throttling or a locked screen.
- A service worker with Background Sync for queued sets — real offline-first logging, but it means
  caching pages (and IndexedDB for the queue) and a second code path for every write; noted as a
  follow-up in the phase doc. Safari has no Background Sync either.
- `POST` per set with server-side de-duplication — ruled out in ADR 0017.
- Asking for notification permission on page load — browsers penalise it and it is rude; it is a
  button on the rest timer instead.

## Consequences
- Sets survive a dropped connection and a reload, but not a page that cannot load at all: the
  workout screen itself still needs the network.
- Two devices editing the same workout do not see each other's unsent rows; the API state wins on
  the next load (rows it has are shown as saved).
- `docs/img` screenshots and the e2e run the screen at phone width (375 px).
