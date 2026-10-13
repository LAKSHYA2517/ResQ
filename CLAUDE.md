# CLAUDE.md — ResQ-AI

Classical-AI rescue simulator for BCSE306L (VIT), covering the whole syllabus in one observable agent.
Full spec: [RESQ_AI_AGENT_BRIEF.md](RESQ_AI_AGENT_BRIEF.md) (section numbers below refer to it). Progress: [PLAN.md](PLAN.md).

## Commands

| Command | What it does |
|---|---|
| `make install` | `uv sync` + `pnpm --dir web install` |
| `make check` | **The gate**: regenerate TS types → ruff + ruff format + mypy + biome → pytest (≥90% cov) + vitest → web build |
| `make test` | pytest + vitest only |
| `make lint` | ruff, ruff format --check, mypy (strict), biome |
| `make types` | Regenerate `web/src/api/schema.d.ts` from the FastAPI OpenAPI schema |
| `make dev` | API `localhost:8000` + web `localhost:5173`, one command, Ctrl-C stops both |
| `make demo` | Headless run of the full workflow, offline (`make demo ARGS="--scenario triage_dilemma --quiet"`) |
| `make bench` | Stub until P5; exits 1 with a message |

Single Python test: `uv run pytest tests/engine/test_x.py::test_name --no-cov`.
Format Python: `uv run ruff format .`; frontend: `pnpm --dir web exec biome check --write src`.

## Layout

```
engine/resq/   pure Python, NO web imports (enforced by tests/engine/test_smoke.py)
  world/ search/ logic/ uncertainty/ planning/ decision/ agent/   trace.py
  (additions to the brief's layout: world/session.py = world tick + events; search/router.py = A* route cache)
api/           FastAPI thin layer over the engine (main.py, routers/, schemas.py, sessions.py, ws.py)
web/           Vite + React 19 + TS strict + Tailwind v4 (src/api/schema.d.ts is generated, never hand-edit)
scenarios/     *.json scenario files (schema: brief §6.1)
tests/         engine/ api/ e2e/
docs/          ARCHITECTURE, SYLLABUS_MAP, VIVA_QA, ETHICS, DEMO_SCRIPT (written in P6; ETHICS in P5)
scripts/       bench.py, demo_headless.py
```

Python is `>=3.12` managed by `uv` (system Python is 3.9 — never use it). `resq` and `api` are installed
editable into `.venv` via hatch, so `import resq` / `import api` work from anywhere under `uv run`.

## Non-negotiables (brief §1)

- **No fabricated output.** Every route/trace/metric/plan/probability in the UI comes from an engine call. No hardcoded demo results.
- **No ML, no LLM in the core.** Classical, explainable AI only.
- **Deterministic.** Randomness only via a seeded RNG stored in scenario/session. Same seed + event log = same run.
- **Every AI function returns `(result, trace)`**; `trace` is a list of typed events (`engine/resq/trace.py`). UI renders traces, never invents them.
- **Real metrics only**: nodes expanded/generated, frontier size, path cost, `perf_counter` wall-clock.
- **Optimality claims are computed** (compare against UCS), never asserted.

## Conventions

- Engine deps: stdlib only (numpy only if Bayes sampling truly needs it). No pydantic/fastapi inside `engine/`; Pydantic models live in `api/schemas.py`.
- Coordinates are `(row, col)`, validated on every mutation.
- Closed-world assumption, Horn clauses, no negation. Base facts rebuilt from state each tick; derived facts recomputed from scratch (no stale facts).
- Deterministic tie-breaking everywhere in search (document the rule next to the code).
- An event dated tick t is part of snapshot t; a user event re-deliberates the current tick (`agent/loop.py: react`). Any new agent behaviour must keep `replay(scenario, log, t) == history`.
- Wall-clock numbers live only in fields declared `compare=False` (`Metrics.timings_ms`, `Plan.time_ms`), never in trace events.
- Trace events hold JSON-friendly primitives only, and no field named `kind`.
- `api/schemas.py` copies engine values; it may group and count, never compute a result.
- `mypy --strict` clean on `engine/`; ruff line length 100; TS `strict` + `noUncheckedIndexedAccess`.
- Tiers: MUST and SHOULD are in scope; COULD only after P6 is done and green.
- Shortcuts with a known ceiling get a `ponytail:` comment naming the ceiling and the upgrade path.

## Workflow rules

- Build phase by phase (brief §11). Run `make check`; do not start the next phase while it is red.
- **Do not commit on your own.** The user commits. When asked, use `phase-N: <summary>`.
- If a spec point is ambiguous, pick the default recorded in PLAN.md "Open questions" and proceed.
- Keep PLAN.md checkboxes current; tick a box only when the acceptance criterion is verified, not when code is written.
