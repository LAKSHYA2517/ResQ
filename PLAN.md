# PLAN.md — ResQ-AI milestones

Source of truth: [RESQ_AI_AGENT_BRIEF.md](RESQ_AI_AGENT_BRIEF.md). Gate for every phase: `make check` green.
Tick a box only when verified. Commits are made by the user (see CLAUDE.md).

## Open questions (defaults applied, change anytime)

1. **Python type checker** — mypy or pyright? *Default: mypy `--strict`* (pure Python, works offline; pyright's PyPI wheel downloads node on first run).
2. **Frontend linter/formatter** — *Default: Biome* (single dependency for lint + format).
3. **numpy** — *Default: not installed.* Stdlib `random.Random(seed)` is enough for sampling; add numpy only if a profile shows it's needed.
4. **API route prefix** — *Default: none*, exactly the paths in brief §8 (`/simulation/start`, `/kb/query`, ...).
5. **Deferred frontend libs** — *Default: install at the phase that uses them* (P3: shadcn/ui, Zustand, TanStack Query, motion; P4: Recharts, React Flow, cmdk; P6: Playwright), not up front.

## Brief-to-test mapping (the "original 10")

Brief §10 lists them in this order; P1/P2 acceptance refers to these numbers.
1 clear route · 2 obstacles · 3 fire avoidance · 4 multi-person priority · 5 blocked exit ·
6 new fire mid-run · 7 no route · 8 evacuation status · 9 hazard removed · 10 search comparison

## P0 — Scaffold, tooling, docs, Makefile
- [x] `CLAUDE.md`, `PLAN.md`
- [x] uv project (Python 3.12), `engine/resq` subpackages per brief §5, `api/` with `/health`
- [x] `web/`: Vite + React 19 + TS strict + Tailwind v4 + Vitest + Biome
- [x] OpenAPI → TS types pipeline (`make types`)
- [x] `Makefile`: `install dev check test lint types` (+ `bench`/`demo` stubs)
- [x] `make check` passes on the empty skeleton; `make dev` serves API :8000 and web :5173

## P1 — World, scenarios, search basics, fire
- [ ] `trace.py` typed events
- [ ] World model: grid, terrain (FLOOR 1 / RUBBLE 3 / WALL / EXIT), FIRE blocked, derived HOT (+4), entities, person status
- [ ] Scenario JSON schema + validation (human-readable errors with cell positions)
- [ ] Fire dynamics: seeded stochastic spread, `p_spread = 0` = static
- [ ] Event-sourced session: scenario + seed + log, replay reproduces identical snapshots
- [ ] Search: BFS, UCS, A* under one `search()` interface; `manhattan × min_cost` heuristic + consistency check
- [ ] All 9 scenarios in `scenarios/*.json`
- [ ] Original tests 1–3, 7, 10 green; replay test green

## P2 — Original plan complete
- [ ] Logic: terms, unification, KB, forward chaining with provenance, core rules
- [ ] Priority function with breakdown + hysteresis δ
- [ ] STRIPS + forward planner; Travel cost from A*
- [ ] Agent loop (OBSERVE … RE-PLAN), events, replanning with reasons, monitor
- [ ] API: scenario / simulation / replay endpoints + WS `/ws/simulation/{id}`
- [ ] `make demo` headless run of the full workflow; original tests 4–9 green

## P3 — Frontend core
- [ ] Scenario builder, canvas, controls, timeline scrubber
- [ ] Reasoning / Search / Planning panels (core)
- [ ] Guided Demo skeleton; inject fire → see replan + reason

## P4 — MUST extensions
- [ ] DFS / DLS / IDDFS / Greedy / weighted A*, Algorithm Race, Heuristic Lab (`/search/compare`, `/search/heuristic-check`)
- [ ] Unification UI, backward chaining + proof tree, resolution refutation, "Prove it" (`/kb/query`)
- [ ] Bayes net: enumeration, variable elimination, rejection / likelihood weighting / Gibbs, convergence (`/bayes/infer`); Risk feeds priority
- [ ] Order optimizer: hill climbing, SA, GA vs greedy vs exhaustive (`/optimize/order`)
- [ ] Adversarial fire: minimax + alpha-beta, same move, pruning counters (`/adversarial/move`)
- [ ] Regression planner; forward = regression cost (`/plan/compare`)
- [ ] Agent/PEAS panel, Syllabus panel with "Run it" buttons
- [ ] Every MUST row of brief §3 runs from the UI and has tests

## P5 — SHOULD
- [ ] Planning graph with mutex links + viewer
- [ ] HTN decomposition tree
- [ ] Baseline agents (reflex / goal / utility), `make bench` real seeded tables (`/bench/agents`)
- [ ] `docs/ETHICS.md`

## P6 — Polish and docs
- [ ] Presentation mode, command palette, run-report export
- [ ] Playwright trace-integrity e2e + full Guided Demo
- [ ] `README.md`, `ARCHITECTURE.md`, `SYLLABUS_MAP.md`, `VIVA_QA.md` (≥25 Q&A), `DEMO_SCRIPT.md`
- [ ] Brief §13 checklist complete; grep confirms no hardcoded demo results

## P7 — COULD (only after P6)
- [ ] Fog-of-war + belief states, D* Lite comparison
- [ ] 2-agent coordination
- [ ] Optional LLM narrator (paraphrases real traces only; off by default)
