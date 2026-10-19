# `make verify` must pass before anything is merged.
# CI runs the same targets.

SHELL := /bin/bash
.DEFAULT_GOAL := help
UV ?= uv

.PHONY: help install lint format typecheck test-unit test-integration test-fault coverage audit verify prod-check demo-check \
        compose-up compose-down compose-smoke loadtest

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-18s %s\n",$$1,$$2}'

install: ## Install all dependencies (locked)
	$(UV) sync --all-groups --frozen

lint: ## ruff lint + format check + import-layer contracts (import-linter)
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run lint-imports

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

prod-check: ## Production compose with dummy secrets: private DB/Redis, gateway allowlist, fail-fast secrets
	uv run python scripts/prod_check.py

demo-check: ## Demo compose: own project, DEMO_MODE, seeded reads and 403 writes through the gateway
	uv run python scripts/demo_check.py

.PHONY: backup-now restore-check restore-check-ci

# mac-prod.sh resolves the image tag (env file, last deploy, running stack, git SHA), so these
# work without TRAINSYNC_TAG in the shell.
backup-now: ## Production: one encrypted backup now + retention (LABEL=predeploy to tag it)
	./scripts/mac-prod.sh compose run --rm backup now $(LABEL)

restore-check: ## Production: restore the newest backup into a scratch DB and compare row counts
	./scripts/restore-check.sh

restore-check-ci: ## Backup image against a seeded DB: good backup restores, bad ones fail (Docker)
	uv run python scripts/restore_check_ci.py

loadtest: ## Compose stack + 5,000 activities, locust 50 users for 2 min, CSV + summary
	./scripts/loadtest.sh

# ---------------------------------------------------------------- Mac production host (Phase 7)

.PHONY: shellcheck doctor public-check

SHELLCHECK_IMAGE := koalaman/shellcheck:v0.10.0
SHELL_SCRIPTS = $(shell find scripts deploy -name '*.sh' | sort)

shellcheck: ## shellcheck every scripts/ and deploy/ shell script (pinned Docker image)
	docker run --rm -v "$(CURDIR):/mnt:ro" -w /mnt $(SHELLCHECK_IMAGE) $(SHELL_SCRIPTS)

doctor: ## Mac production host health: Docker, sleep, disk, Tailscale/Funnel, agent, backups
	./scripts/mac-prod.sh doctor

.PHONY: deploy rollback

deploy: ## Production: clean main == origin/main + green CI -> build, backup, migrate, up, smoke test
	./scripts/deploy.sh deploy

rollback: ## Production: previous deploy's images back (downgrades reversible migrations first)
	./scripts/deploy.sh rollback

public-check: ## From outside: TLS, allowlisted routes forwarded, the rest 404 (URL=https://<host>.ts.net)
	@test -n "$(URL)" || { echo "usage: make public-check URL=https://<host>.ts.net" >&2; exit 2; }
	$(UV) run python scripts/public_check.py --url "$(URL)"

# ---------------------------------------------------------------- web dashboard (web/)

.PHONY: web-verify web-e2e

# Dummy secrets for the build: after `pnpm build`, check-bundle fails if any of them shows up in a
# browser-served file (.next/static, public/).
WEB_CANARY_ENV := DASHBOARD_SESSION_SECRET=web-verify-canary-session-secret-5b7c0e2a4d6f8a1c

web-verify: ## Web: install (locked) + lint + typecheck + unit tests + build + no-secret-in-bundle check
	cd web && pnpm install --frozen-lockfile && pnpm lint && pnpm typecheck && pnpm test \
		&& $(WEB_CANARY_ENV) pnpm build && $(WEB_CANARY_ENV) pnpm check:bundle

web-e2e: ## Web: compose stack + Playwright e2e (fake Strava), screenshots to docs/img, tear down
	./scripts/web_e2e.sh
