# One image for api, worker, migrate and fake-strava; the compose command picks the role.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime
RUN useradd --system --uid 10001 --user-group --no-create-home app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY fake_strava ./fake_strava
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER app
EXPOSE 8000
# One image, several roles: each role points HEALTHCHECK_URL at what proves it is alive
# (the worker at its metrics port); one-shot roles disable the check in compose.
ENV HEALTHCHECK_URL=http://127.0.0.1:8000/health/live
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(os.environ['HEALTHCHECK_URL'], timeout=2)"]
CMD ["uvicorn", "trainsync.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
