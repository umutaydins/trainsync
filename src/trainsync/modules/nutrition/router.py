"""`/v1/nutrition`: foods (local + Open Food Facts lookup), food log, profile, summaries.

Energy balance is an estimate (ADR 0019); see `routes/summary.py`. The schemas live in
`schemas/`, the route groups in `routes/`.
"""

from fastapi import APIRouter

from trainsync.modules.nutrition.routes import favorites, foods, log, lookup, profile, summary

ROUTERS: tuple[APIRouter, ...] = (
    foods.router,
    lookup.router,
    favorites.router,
    log.router,
    profile.router,
    summary.router,
)
