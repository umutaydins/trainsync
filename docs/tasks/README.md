# Tasks

The four phases in `docs/phases/` broken into small, PR-sized tasks. Do them in id order;
`depends_on` in each file's front matter says what must be merged first. The last task of each
phase is a gate that re-checks every acceptance criterion of that phase.

Each file has the same sections: Goal, Context, Scope, Out of scope, Acceptance criteria, Verify.
A task is done when every acceptance criterion is proven by a test or command and `make verify`
is green.

| Phase | Tasks |
|---|---|
| 1 — Foundation, OAuth, Strava client | P1.1 – P1.9 |
| 2 — Sync engine | P2.1 – P2.6 |
| 3 — Webhooks and read API | P3.1 – P3.7 |
| 4 — Observability, load test, CI, README | P4.1 – P4.5 |

Dependency graph:

```mermaid
flowchart LR
    P1.1 --> P1.2 & P1.3 & P1.4
    P1.4 --> P1.5
    P1.2 & P1.3 & P1.5 --> P1.6 --> P1.7 --> P1.8 --> P1.9
    P1.9 --> P2.1 --> P2.2 --> P2.3 & P2.4
    P2.4 --> P2.5
    P2.3 & P2.5 --> P2.6
    P2.6 --> P3.1 --> P3.2 --> P3.3 --> P3.4 & P3.5
    P3.5 --> P3.6
    P3.4 & P3.6 --> P3.7
    P3.7 --> P4.1 --> P4.2 --> P4.3 --> P4.4 --> P4.5
```
