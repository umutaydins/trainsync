# `make verify` must pass before anything is merged.
# CI runs the same targets.

SHELL := /bin/bash
.DEFAULT_GOAL := help
UV ?= uv

.PHONY: help install lint format typecheck test-unit test-integration test-fault coverage audit verify \
        compose-up compose-down compose-smoke loadtest

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-18s %s\n",$$1,$$2}'

install: ## Install all dependencies (locked)
	$(UV) sync --all-groups --frozen

lint: ## ruff lint + format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format: ## Auto-fix lint and format
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

typecheck: ## mypy strict on src/
	$(UV) run mypy

# pytest exits with 5 when no tests are collected; that is fine for an empty suite.
define run_pytest
	$(UV) run pytest $(1); code=$$?; if [ $$code -eq 5 ]; then echo "no tests collected for: $(1)"; exit 0; fi; exit $$code
endef

# Coverage: each suite only collects data (a single suite is below the bar on its own);
# `make coverage` enforces fail_under = 85 (pyproject) on unit + integration combined.
test-unit: ## Unit tests (no Docker); starts fresh coverage data
	@$(call run_pytest,-m "not integration and not fault" --cov --cov-report= --cov-fail-under=0)

test-integration: ## Integration tests (Docker required: testcontainers); adds to coverage data
	@$(call run_pytest,-m "integration and not fault" --cov --cov-append --cov-report= --cov-fail-under=0)

test-fault: ## Fault-injection suite (Docker required)
	@$(call run_pytest,-m fault)

coverage: ## Branch coverage of unit + integration over src/ (fails under 85%), writes coverage.xml
	$(UV) run coverage report
	$(UV) run coverage xml -q

audit: ## Known-vulnerability check of every locked dependency (pip-audit)
	$(UV) export --frozen --all-groups --no-emit-project --format requirements-txt \
		> .audit-requirements.txt
	uvx pip-audit --strict --disable-pip --require-hashes -r .audit-requirements.txt; \
		code=$$?; rm -f .audit-requirements.txt; exit $$code

verify: lint typecheck test-unit test-integration coverage ## Everything CI checks. Must be green.
	@echo "verify: OK"

compose-up: ## Start the local stack
	docker compose up -d --build

compose-down: ## Stop the local stack and drop volumes
	docker compose down -v

compose-smoke: ## Start the stack, run the OAuth smoke test, tear it down
	./scripts/compose_smoke.sh

loadtest: ## Compose stack + 5,000 activities, locust 50 users for 2 min, CSV + summary
	./scripts/loadtest.sh

# ---------------------------------------------------------------- web dashboard (web/)

.PHONY: web-verify web-e2e

# Dummy secrets for the build: after `pnpm build`, check-bundle fails if any of them shows up in a
# browser-served file (.next/static, public/).
WEB_CANARY_ENV := TRAINSYNC_API_KEY=web-verify-canary-api-key-3f9a1c \
	DASHBOARD_PASSWORD=web-verify-canary-password-8d2e \
	DASHBOARD_SESSION_SECRET=web-verify-canary-session-secret-5b7c0e2a4d6f8a1c

web-verify: ## Web: install (locked) + lint + typecheck + unit tests + build + no-secret-in-bundle check
	cd web && pnpm install --frozen-lockfile && pnpm lint && pnpm typecheck && pnpm test \
		&& $(WEB_CANARY_ENV) pnpm build && $(WEB_CANARY_ENV) pnpm check:bundle

web-e2e: ## Web: compose stack + Playwright e2e (fake Strava), screenshots to docs/img, tear down
	./scripts/web_e2e.sh
