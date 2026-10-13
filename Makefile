.PHONY: install dev check test lint types bench demo

install:
	uv sync
	pnpm --dir web install

# OpenAPI -> TS types, so frontend and backend cannot drift.
types:
	uv run python -c "import json; from api.main import app; print(json.dumps(app.openapi()))" \
		| pnpm --dir web exec openapi-typescript -o src/api/schema.d.ts

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	pnpm --dir web lint

test:
	uv run pytest
	pnpm --dir web test

# Single local gate: types sync, lint, python types, tests, frontend build.
check: types lint test
	pnpm --dir web build

# API on :8000 and web on :5173 together; Ctrl-C stops both.
dev:
	@trap 'kill 0' EXIT INT TERM; \
	uv run uvicorn api.main:app --reload --port 8000 & \
	pnpm --dir web dev & \
	wait

bench:
	@echo "bench: not implemented until Phase 5"; exit 1

# Headless run of the full workflow (offline). Extra flags: make demo ARGS="--scenario triage_dilemma"
demo:
	uv run python scripts/demo_headless.py $(ARGS)
