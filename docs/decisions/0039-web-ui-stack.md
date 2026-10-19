# 0039 — Web UI stack: Tailwind v4 tokens, shadcn-style primitives, next-intl, mobile-first shell

- Status: accepted
- Date: 2026-10-19

## Context
Phase 8 turns the dashboard into a multi-user app that is mostly used one-handed on a phone in the
gym: logging sets, a rest timer, food, the week's progress. The Phase 5 pages were a plain desktop
dashboard (top links, light/dark from the system only, English strings inline). Every user now
has their own language (`/v1/me/settings`), the progress API (ADR 0038) needs charts, and the app
must be installable and pass accessibility checks.

## Decision
- **Styling.** Keep Tailwind CSS v4. Design tokens (colour, radius, spacing, type scale, shadows,
  motion durations) are defined once in `src/styles/tokens.css` as CSS variables, mapped into
  Tailwind with `@theme inline`; components use the token utilities only (no raw hex colours).
  Dark-first with a full light theme, chosen by a `theme` cookie (`system` by default) so the
  server renders the right one without a flash. One electric accent on near-black / off-white.
- **Primitives.** shadcn/ui style: Radix primitives (`radix-ui`) wrapped in our own components in
  `src/components/ui/`, copied into the repo, variants with `class-variance-authority`, class
  merging with `tailwind-merge`. Bottom sheets are `vaul` drawers on mobile and dialogs on desktop
  (one `ResponsiveSheet`). No other UI kit.
- **Motion.** `motion` for page transitions, number count-ups, the timer ring and set feedback;
  every animation respects `prefers-reduced-motion`.
- **Charts.** Recharts (already used), themed through the tokens, touch tooltips, readable at
  375 px.
- **Icons and type.** `lucide-react`; Geist Sans / Geist Mono via `next/font` (the `geist`
  package: self-hosted, no font request at build or run time) with tabular figures for numbers.
- **i18n.** `next-intl` without locale routing: the locale comes from the signed-in user's
  `lang` setting (cached in a `lang` cookie by the BFF), else `Accept-Language`, else English.
  Messages live in `src/i18n/messages/<locale>/<namespace>.json`, one file per feature, so
  features never edit a shared file; a test checks both languages have the same keys.
- **Shell.** Bottom tab bar on mobile (Today, Workout, Food, Progress, Me), sidebar on desktop,
  safe-area insets, 44 px touch targets. Owner-only items are rendered only for the owner.
- **PWA.** The existing manifest plus a minimal service worker that caches the app shell and an
  offline page; API responses are never cached (personal data).
- **Boundaries.** ESLint rules extend ADR 0033: `app/` routes are thin; `features/<domain>/`
  hold components, hooks and server actions; `i18n/` and `styles/` are leaves.

## Alternatives considered
- A component kit (MUI, Chakra, Mantine) — heavier bundles, a look that is hard to make our own,
  and a second styling system next to Tailwind.
- Locale-prefixed routes (`/tr/...`) — the language is a user setting, not part of the URL, and
  the BFF already knows the user; prefixes would double every route and the e2e paths.
- Google-hosted fonts through `next/font/google` — needs network at build time on every machine;
  the `geist` package ships the files.
- A full offline mode with cached API data — personal data on shared devices, and stale numbers
  in the gym are worse than an honest "offline" screen.

## Consequences
- New pages compose primitives and tokens; a design change is a token change.
- Two message files per feature must stay in sync (tested).
- The service worker must be versioned with the build; a stale shell is cleared on activation.
