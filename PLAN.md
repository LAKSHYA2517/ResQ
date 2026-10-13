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
- [x] `trace.py` typed events
- [x] World model: grid, terrain (FLOOR 1 / RUBBLE 3 / WALL / EXIT), FIRE blocked, derived HOT (+4), entities, person status
- [x] Scenario JSON schema + validation (human-readable errors with cell positions)
- [x] Fire dynamics: seeded stochastic spread, `p_spread = 0` = static
- [x] Event-sourced replay (`world/session.py`): scenario + seed + log reproduces identical snapshots
- [x] Search: BFS, UCS, A* under one `search()` interface; `manhattan × min_cost` heuristic + `check_heuristic`
- [x] All 9 scenarios in `scenarios/*.json`
- [x] Original tests 1–3, 7, 10 green; replay test green (`make check`: 92 pytest, 97% engine coverage)

P1 decisions worth remembering (details go in `docs/ARCHITECTURE.md` in P6):
- Entering a cell costs terrain cost (+4 if Hot); exits are passable cells, `EXIT_BLOCKED` only makes them unusable as drop-offs.
- Tick order in `advance`: events due at this tick (scripted, then logged) → fire spread → status settle → `tick += 1`. P2 inserts the agent's ACT before events.
- RNG per tick is `Random(f"{seed}:{tick}")`, so any tick is reproducible without replaying the RNG stream.
- A `WAITING` person on a fire cell becomes `TRAPPED` (and reverts if the fire is extinguished). "Cut off" trapping is derived by the KB from search in P2.
- Search tie-break: lowest f, then lowest h, then first generated; successors in U, D, L, R order. BFS tests the goal at generation (AIMA); UCS/A* at expansion. Closed nodes are re-opened if g improves, so A* is optimal for any admissible h.
- Events that conflict with the state are *rejected with a trace entry* rather than raising, so a scripted event can never crash a run.
- **P4 tuning to do:** in Showcase, BFS already matches UCS on the far critical person p2 (cost 13). When DFS/Greedy land, check they differ there for demo step 7; if not, add rubble on p2's direct route.

## P2 — Original plan complete
- [x] Logic: terms + parser, unification (MGU, occurs check), KB with provenance, forward chaining to a fixpoint, the 10 core rules
- [x] Priority function with breakdown + hysteresis δ (`decision/priority.py`)
- [x] STRIPS + forward planner (A* over states, admissible heuristic); Travel cost and path from A*
- [x] Agent loop (OBSERVE … RE-PLAN), execution monitor, events, replanning with reasons
- [x] API: scenario / simulation / replay endpoints + WS `/ws/simulation/{id}`; OpenAPI → TS types regenerated
- [x] `make demo` headless run of the full workflow; original tests 4–9 green (`make check`: 185 pytest, 99% engine coverage; 14/14 mutation spot-checks killed)

P2 decisions worth remembering:
- **Timeline rule:** an event dated tick t is part of snapshot t. Tick t→t+1 = ACT → fire spread → clock → scripted events of t+1 → deliberate. A *user* event lands on the current tick and triggers a second deliberation of that tick (`react`), so the agent's just-made plan is re-validated and the replan reason is real even at tick 0. Replay reproduces this exactly (`replay(scenario, log, t) == history`).
- **Reasoning ↔ search loop:** A* (agent → each waiting person) gives `Reachable(P)` and the real path cost; `Urgent(P)` is asserted when time-grown urgency ≥ threshold. Both enter the KB as base facts because Horn clauses over symbols cannot search or do arithmetic. `Eligible(P)` is then *derived*.
- **Closed world, no negation in rules.** "Exit is open" is the query `not Unavailable(e)` (absence from the KB), never a rule body. `Hot(X)` in the KB also holds for burning cells next to other burning cells (no way to say "and not Fire(X)"); the cost model uses `State.hot`, which excludes fire.
- **Plan = single-target** `[Travel, PickUp, Travel, DropOff]` chosen by the planner (it picks the exit). The planner itself is general (multi-person goals work and are tested); P4's `/plan/compare` and the order optimizer use that.
- **When the agent replans:** (1) `invalid`: a stored route cell is blocked or a STRIPS precondition fails against live facts (no search needed to detect); (2) `target_switch`: hysteresis says another person is better by more than δ; (3) `cheaper`: the world layout changed and a strictly cheaper plan exists. With a static world there are zero planner calls between events.
- **Metrics are a pure function of the run** (the A* cache lives for one deliberation only), so replay reproduces them too; only `timings_ms` is excluded from equality.
- Snapshots carry decision-level traces (routes computed, plan found, target chosen, plan invalidated/adopted, action, events). Per-node search/plan traces and per-rule firings are returned by the functions themselves and will be served on demand by P4 endpoints; derivations (with rule, bindings, premises, pass number) are always in the snapshot.
- API omits the static `Adjacent(…)` facts from `facts` (they are counted in `fact_counts`); everything else is passed through untouched.
- Scenario tuning (re-check after any change to agent behaviour): Showcase `p_spread 0.04, seed 24` → 3/3 rescued with `cheaper`, `invalid`, `cheaper` replans; Spreading Fire `p_spread 0.08, seed 3` → 1/2 rescued, ends stuck while carrying p1 (no route to the exit).
- Trace event dataclasses must not have a field called `kind` (it is the base-class property).

## P3 — Frontend core
- [x] Scenario builder: palette, drag-paint, erase, undo/redo (one step per drag), grid size, predefined loader, import/export JSON, browser library, inline engine validation with the offending cells outlined
- [x] Canvas (Canvas 2D): terrain patterns, hot-zone stripes, flickering fire, agent glide, people with status badges, exits with usable/blocked state, animated route, plan waypoints, trail, explored-cell heat overlay, target ring
- [x] Controls: start / pause / resume / step / reset / speed, timeline scrubber (read-only time travel), event injector (click-to-place or exit), event log with replan reasons
- [x] Reasoning panel (facts, rules with derived counts, derived facts with provenance, fact diff after an event, structured state) · Search panel (comparison table, bars, explored overlay) · Planning panel (goal, priority breakdown, plan with step status, replan card, no-plan reasons)
- [x] "Explain this decision / route / replan" dialog showing the engine's own trace
- [x] Guided Demo: 14 steps, each a real API call; steps for later phases are listed as "arrives in Phase N", not faked
- [x] Acceptance: `tests/e2e/flow.spec.ts` (Playwright) loads a scenario, plays it, injects a fire, and checks the replan reason against the API; `make check` 190 pytest + 44 vitest; `make e2e` 3 passed

New API surface in P3: `GET /kb/rules`, `POST /search/compare` (BFS/UCS/A* × heuristics at any tick), `GET /simulation/log` (event log built from engine traces).

P3 decisions worth remembering:
- The browser holds no simulation logic. The Zustand store mirrors API responses; the cache of ticks only feeds the scrubber and trail. Scrubbing a tick the client has not seen calls `/simulation/replay/{tick}`.
- Builder preview shows no Hot zones: that is derived by the engine once the scenario is started.
- Playwright specs live in `tests/e2e` (brief layout) and import from `web/node_modules` through `NODE_PATH`, which `make e2e` sets. `e2e` is not yet part of `make check`; P6 folds the trace-integrity run into the gate.
- Component tests render real engine snapshots from `web/src/test/fixtures.json` (generated by running the engine; regenerate it when the snapshot schema changes).
- Fire-spread lines are hidden in the event log by default (a checkbox shows them); they remain in the API log.
- Left for P6: presentation mode, command palette, run-report export. Left for P4: Syllabus/Agent/Optimize/Uncertainty tabs, race view, heuristic lab, "Prove it".

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
