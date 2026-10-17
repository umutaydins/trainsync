# `make verify` must pass before anything is merged.
# CI runs the same targets.

SHELL := /bin/bash
.DEFAULT_GOAL := help
UV ?= uv

.PHONY: help install lint format typecheck test-unit test-integration test-fault verify \
        compose-up compose-down compose-smoke

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

test-unit: ## Unit tests (no Docker)
	@$(call run_pytest,-m "not integration and not fault")

test-integration: ## Integration tests (Docker required: testcontainers)
	@$(call run_pytest,-m "integration and not fault")

test-fault: ## Fault-injection suite (Docker required)
	@$(call run_pytest,-m fault)

verify: lint typecheck test-unit test-integration ## Everything CI checks. Must be green.
	@echo "verify: OK"

compose-up: ## Start the local stack
	docker compose up -d --build

compose-down: ## Stop the local stack and drop volumes
	docker compose down -v

compose-smoke: ## Start the stack, run the OAuth smoke test, tear it down
	./scripts/compose_smoke.sh
