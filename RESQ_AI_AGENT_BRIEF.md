# ResQ-AI — Agent Brief for Claude Code

> Audience: Claude Code, building the project end to end.
> Course: BCSE306L Artificial Intelligence (VIT). Textbook: Russell & Norvig, AIMA 3e.
> Goal: a classical-AI rescue simulator that covers the **whole syllabus** in one observable agent, so the evaluator can see every module working on screen and trace every decision to real engine output.

---

## 0. How to work

1. Read this whole brief before writing code.
2. Create `CLAUDE.md` (commands, conventions, layout) and `PLAN.md` (milestone checklist). If something is truly ambiguous, put at most 5 questions in `PLAN.md` with a default for each, and proceed with the defaults.
3. Build phase by phase (Section 11). After each phase run `make check` (lint + types + tests). Do not start the next phase while it is red. Commit as `phase-N: <summary>`.
4. The **engine is a pure Python package with zero web dependencies**. The API and UI are thin layers. This is the part the student defends in viva.
5. Tiers: **MUST** and **SHOULD** are in scope. **COULD** only if everything above is finished, tested and documented. Cut COULD first when time is short.
6. If two developers: agree the API schema (Section 8) first, then split engine vs web.

## 1. Non-negotiables

- **No fabricated output.** Every route, trace line, metric, plan and probability shown in the UI comes from an engine call. Never hardcode demo results.
- **No ML, no LLM in the core.** Classical AI only. Everything explainable.
- **Deterministic.** All randomness uses a seeded RNG stored in the scenario/session. The same seed + same event log reproduces the same run.
- **Every AI function returns `(result, trace)`**, where `trace` is a list of typed events. The UI renders traces; it never invents them.
- **Real metrics only:** nodes expanded/generated, frontier size, path cost, wall-clock time measured with `perf_counter`.
- Every claim of optimality in the UI is computed (compare against UCS), not asserted.

## 2. Review of the original plan: what changes and why

The original plan is solid on integration. These are the fixes and upgrades.

| # | Issue in original | Fix |
|---|---|---|
| F1 | A person standing on a fire cell is "at risk", but fire cells are impassable, so that person can never be reached. The example contradicts the rules. | Fire = impassable. Add a derived **Hot zone** (cells adjacent to fire): passable at a high cost and flagged unsafe. "At risk" = person in a Hot zone. A person *on* a fire cell is `TRAPPED` (unreachable), set by the KB. Validation forbids placing a person on fire at start; fire spread can later trap them. |
| F2 | On a uniform grid BFS = UCS = A* in path cost, so the comparison is boring. | Add terrain costs (floor 1, rubble 3, Hot zone +4). Now UCS ≠ BFS and the comparison is meaningful. |
| F3 | Priority uses Manhattan distance. | Use real path cost from A*. Reachability from search is written back into the KB as `Reachable(P)`; eligibility is derived by a rule. Reasoning ↔ search form a loop. |
| F4 | Priorities recalculated every event can make the agent flip targets repeatedly. | Urgency grows with waiting time; switching target requires a margin (hysteresis δ). Log every switch with the reason. |
| F5 | Planner is a hand-written list of steps. | Real STRIPS-style planner (forward + backward search), planning graph, HTN decomposition. Abstract plan with A* as the low-level Travel action. |
| F6 | Syllabus gaps: DFS, DLS, IDDFS, Best-First, local search, adversarial search, unification, backward chaining, resolution, Bayesian nets (only "optional"), planning graphs, hierarchical and multi-agent planning. | Added (Section 3). |
| F7 | Fire is static between user events. | Fire spreads stochastically (seeded). Environment becomes dynamic + stochastic, which justifies replanning and Bayesian reasoning. |
| F8 | Agent capacity is undefined. | Agent carries **one person at a time**: pick up → exit → drop off. |
| F9 | KB semantics unspecified (negation, stale facts). | **Closed-world assumption**, Horn clauses only (no negation). Separate *base facts* (from state) from *derived facts* (recomputed from scratch each tick). No stale facts possible. |
| F10 | "Adjust heuristic if costs change" is vague. | `h = Manhattan × min_step_cost`. Tests assert consistency: `h(n) ≤ c(n,n') + h(n')`. |
| F11 | No reproducibility or replay. | Event-sourced simulation: initial scenario + seed + action/event log = full replay and time-travel scrubber. |

## 3. Syllabus coverage map (the "impress the teacher" spine)

The app must include a **Syllabus panel** that lists this table, with a live "Run it" button per row that jumps to the feature.

| Module | Syllabus topics | Feature in ResQ-AI | Tier |
|---|---|---|---|
| 1 Intro | Intelligent agents, structure of agents, environments | **Agent & Environment Profile** panel: PEAS table, environment properties (observable / deterministic / episodic / static / discrete / single-vs-multi-agent) that update live with the mode toggled. **Agent-type benchmark**: simple-reflex vs goal-based vs utility-based on identical scenarios. | MUST |
| 2 Search | State space, BFS, UCS, DFS, DLS, IDDFS, Best-First (greedy), A* | All eight implemented under one interface. **Algorithm Race**: same scenario, side-by-side animated exploration with live counters. Heuristic lab: Manhattan vs Euclidean vs zero vs weighted (inadmissible) with admissibility/consistency check. | MUST |
| 3 Local + adversarial | Hill climbing, simulated annealing, genetic algorithm, game trees, minimax, alpha-beta | **Rescue-order optimizer** (hill climbing with restarts, SA, GA) vs greedy vs exhaustive optimum. **Adversarial Fire mode**: fire plays MAX, agent plays MIN, minimax with alpha-beta; show nodes with vs without pruning. | MUST |
| 4 Logic | Propositional, FOL, unification, forward chaining, backward chaining, resolution | FOL-lite Horn-clause KB with variables and **unification**; forward chaining with provenance; **backward chaining** with proof tree; **resolution refutation** console ("Prove it"). | MUST |
| 5 Uncertainty | Bayes rule, Bayesian networks, approximate inference | **Sensor Bayesian network** (fire → smoke/heat sensors; trapped → voice detection). Exact inference (enumeration + variable elimination) and approximate (rejection sampling, likelihood weighting, Gibbs). Posterior feeds `Risk(P)`. Convergence plot of approximate → exact. | MUST |
| 6 Planning | Classical planning, forward/backward state-space search, planning graphs, hierarchical planning, nondeterministic domains, sensorless, multi-agent | STRIPS domain; forward planner; backward (regression) planner; planning-graph viewer; HTN decomposition tree; execution monitoring + replanning (nondeterministic); optional fog-of-war belief states; optional 2-agent coordination. | MUST (strips, fwd, bwd) / SHOULD (graph, HTN) / COULD (fog, multi-agent) |
| 7 Communicating, perceiving | NLP, perception | Out of scope. Say so in the docs. Sensors are simulated inputs to the Bayes net. | n/a |
| 8 Contemporary issues | Ethics, current issues | `docs/ETHICS.md` and a slide: triage ethics, why priority weights are simulation values, limits of classical AI vs learning-based agents. | SHOULD |

## 4. Tech stack (modern, boring where it counts)

**Backend / engine**
- Python 3.12+, **uv** for env and deps, **FastAPI**, **Pydantic v2**, Uvicorn
- WebSocket for streaming simulation ticks (REST for everything else)
- **pytest** + **hypothesis** (property tests), **ruff** (lint + format), **pyright** or mypy (strict on `engine/`)
- Engine deps: stdlib + `numpy` only (optional, for Bayes sampling). Nothing else.

**Frontend**
- **Vite + React 19 + TypeScript (strict)**, **Tailwind CSS v4**, **shadcn/ui** (Radix primitives)
- **Zustand** (UI state) + **TanStack Query** (REST)
- Grid rendering on **HTML Canvas 2D** (or PixiJS if frame rate demands); panels in React
- **motion** (Framer Motion) for panel transitions; **Recharts** for metrics; **React Flow (xyflow)** for proof trees, planning graph, Bayes net, HTN tree; **cmdk** for command palette
- Types generated from the FastAPI OpenAPI schema (`openapi-typescript`) so frontend and backend cannot drift
- **Vitest** + **Playwright** (one e2e that runs the full demo)

**Tooling**
- `pnpm`, `Makefile` (`make dev`, `make check`, `make test`, `make bench`, `make demo`)
- **Local-only.** The project is demoed on localhost. No Docker, no CI pipeline, no cloud deployment. `make dev` must start the API (`localhost:8000`) and the web app (`localhost:5173`) together with one command, and `make demo` must work offline.

## 5. Repository layout

```
resq-ai/
├─ engine/resq/                  # pure Python, no web imports
│  ├─ world/        grid.py state.py terrain.py fire.py events.py scenarios.py
│  ├─ search/       problem.py uninformed.py informed.py heuristics.py
│  │                adversarial.py local.py
│  ├─ logic/        terms.py unify.py kb.py rules.py forward.py backward.py resolution.py
│  ├─ uncertainty/  bayesnet.py exact.py sampling.py models.py
│  ├─ planning/     strips.py domain.py fwd_planner.py regression.py
│  │                planning_graph.py htn.py monitor.py
│  ├─ decision/     priority.py ordering.py
│  ├─ agent/        agent.py loop.py baselines.py multi.py(COULD)
│  └─ trace.py                   # typed trace events
├─ api/             main.py routers/ schemas.py sessions.py ws.py
├─ web/             Vite React app (see Section 9)
├─ scenarios/       *.json (schema in Section 6.1)
├─ tests/           engine/ api/ e2e/
├─ docs/            README assets, ARCHITECTURE.md, SYLLABUS_MAP.md, VIVA_QA.md, ETHICS.md, DEMO_SCRIPT.md
├─ scripts/         bench.py  demo_headless.py
├─ CLAUDE.md  PLAN.md  Makefile
```

## 6. Engine specification

### 6.1 World model

- Grid 5×5 to 30×30 (default 10×10). Coordinates `(row, col)`, validated on every mutation.
- Cell terrain: `FLOOR` (cost 1), `RUBBLE` (cost 3, passable), `WALL` (blocked), `EXIT`.
- Hazards: `FIRE` (blocked). Derived: `HOT` (4-neighbour of fire; passable, +4 cost, unsafe).
- Entities: one agent (carries ≤ 1 person), people `{id, pos, risk, urgency, status}`, exits `{id, pos, available}`.
- Person status: `WAITING → CARRIED → EVACUATED`, or `TRAPPED` (on fire cell / cut off).
- Fire dynamics: each tick, every fire-frontier cell ignites each non-wall neighbour with probability `p_spread` (scenario parameter, seeded RNG). Fire never spawns on the agent's cell. `p_spread = 0` gives the static original behaviour.
- Cost model is a config object; defaults documented in `docs/ARCHITECTURE.md`.
- Scenario JSON: `{name, grid_size, terrain, agent, people[], fire[], exits[], scripted_events[{tick, type, args}], seed, params{p_spread, weights, cost_model}}`.
- Validation: agent placed, ≥1 person, ≥1 exit, coordinates in range, no incompatible overlaps, every person/exit not on fire/wall at start. Return a list of human-readable errors with cell positions.
- Predefined scenarios (ship all): Basic Rescue, Fire Emergency, Multiple People, Blocked Exit, Dynamic Emergency, **Spreading Fire**, **Triage Dilemma** (near-safe vs far-critical), **Impossible** (no route, tests failure reporting), **Showcase** (the demo scenario, tuned so every panel has something interesting).

### 6.2 Search (Module 2)

One interface: `search(problem, algorithm, heuristic=None, **opts) -> (SearchResult, Trace)`.

- Algorithms: `bfs, dfs, dls(limit), iddfs, ucs, greedy, astar, weighted_astar(w)`.
- Graph search with an explored set; deterministic tie-breaking (documented).
- `SearchResult`: `found, path, cost, expanded, generated, max_frontier, time_ms, expansion_order[], optimal_vs_ucs: bool|None`, plus capped frontier snapshots for animation.
- Heuristics: `manhattan × min_cost`, `euclidean`, `zero`, `weighted(w)`. A `check_heuristic(problem, h)` util returns admissibility and consistency violations over the grid (used by the Heuristic Lab UI).
- DFS/DLS/greedy are expected to be non-optimal in some scenarios; the comparison table must show that honestly.
- `POST /search/compare` runs any subset on the same scenario, returns a table plus traces.

### 6.3 Local and adversarial search (Module 3)

**Rescue-order optimizer** (`decision/ordering.py`, `search/local.py`)
- Problem: order `k` people (and nearest-feasible exit per person) to minimize `Σ priority_i × completion_time_i`, using a pairwise A* cost matrix.
- Algorithms: hill climbing (swap/insert neighbours, random restarts), simulated annealing (geometric cooling, exposed params), genetic algorithm (order crossover, swap mutation, tournament selection).
- Baselines: greedy-by-priority and **exhaustive optimum for k ≤ 7**.
- Return convergence curves (best fitness per iteration/generation). UI plots them with the optimum as a reference line.

**Adversarial Fire mode** (`search/adversarial.py`)
- Two-player zero-sum model: agent minimizes cost-to-complete-current-leg; fire (MAX) ignites up to `k` frontier cells per turn to maximize it (∞ if the agent is cut off).
- Depth-limited **minimax** and **minimax with alpha-beta**. Leaf evaluation = cached A* / Manhattan lower bound. Expose depth.
- Report nodes visited with vs without pruning. Same move must be chosen by both (test).
- It is a toggle: normal mode = stochastic fire, adversarial mode = worst-case fire.

### 6.4 Logic and reasoning (Module 4)

FOL-lite, Horn clauses, closed-world assumption.
- `terms.py`: constants (lowercase/IDs), variables (Uppercase), predicates, atoms.
- `unify.py`: most general unifier with occurs check; `substitute`, `compose`.
- `kb.py`: base facts (rebuilt from state every tick) + rules + derived facts with **provenance** `{fact, rule, bindings, premises[]}`.
- `forward.py`: fixpoint forward chaining; no duplicate facts; per-iteration trace.
- `backward.py`: SLD backward chaining with proof tree output (`ProofNode{goal, rule, children, bindings}`).
- `resolution.py`: resolution refutation. Convert the *relevant grounded subset* to CNF (propositional case first; FOL with unification for the Horn subset). Show each resolvent and the empty clause. Keep it tractable by restricting to facts relevant to the query.

Core rules (extend, but keep these):
```
Fire(X)                         -> Unsafe(X)
Adjacent(X,Y) & Fire(Y)         -> Hot(X)
Hot(X)                          -> Unsafe(X)
Person(P,X) & Unsafe(X)         -> AtRisk(P)
Person(P,X) & Fire(X)           -> Trapped(P)
Exit(E,X) & Fire(X)             -> Unavailable(E)
Exit(E,X) & Blocked(X)          -> Unavailable(E)
Waiting(P) & Reachable(P)       -> Eligible(P)
AtRisk(P) & Urgent(P)           -> Critical(P)
Eligible(P) & Critical(P)       -> RescueNow(P)      # candidate flag, still ranked by priority score
```
`Reachable(P)` is asserted from search results. At-risk ≠ must-rescue-first; the ranking stays in `priority.py`.

**"Prove it" console:** the user types a goal (e.g. `AtRisk(p2)` or `Eligible(P)`), the app shows the forward trace, the backward proof tree and (for ground goals) the resolution refutation, all from the engine via `POST /kb/query`.

### 6.5 Uncertainty (Module 5)

- `bayesnet.py`: discrete nodes, CPTs, topological order. Validation (CPT rows sum to 1).
- Default model per observation zone: `Fire → Smoke`, `Fire → HeatSensor`, `Fire → Trapped`, `Trapped → VoiceDetected` (editable in UI).
- Inference: enumeration, variable elimination (exact); rejection sampling, likelihood weighting, Gibbs (approximate). Seeded.
- `Risk(P) = round(5 × P(Trapped | evidence))`, which feeds the priority function. Evidence comes from the simulated sensors in the scenario; sensor noise is a parameter.
- UI: network diagram, editable CPTs, evidence toggles, exact posterior bars, and a convergence chart of sample count vs error against the exact value (computed, not drawn).

### 6.6 Decision: priority function (`decision/priority.py`)

```
Priority(P) = w_r·Risk(P) + w_u·Urgency(P,t) − w_d·PathCost(agent→P)
Urgency(P,t) = base_urgency + γ·ticks_waiting   (capped)
```
- Weights configurable per scenario; defaults `w_r=5, w_u=3, w_d=1`.
- Eligible = `Eligible(P)` derived by the KB. Tie-break: lower path cost, then ID.
- Switch target only if `new_priority > current_priority + δ` (δ configurable).
- Always return a human-readable breakdown: `P2: 5×4 + 3×3 − 10 = 19`. Not medical, simulation values only (say so in the UI).

### 6.7 Planning (Module 6)

Two levels: abstract rescue plan (STRIPS) over waypoints, with A* for the concrete `Travel` cost and path.

- `strips.py`: `Action{name, params, pre, add, del, cost}`, ground state = frozenset of atoms.
- Abstract domain: predicates `At(l), Carrying(p), HandsFree, Waiting(p), Evacuated(p), ExitOpen(e)`; actions `Travel(a,b)` (cost from A*, precondition: path exists), `PickUp(p)`, `DropOff(p,e)`.
- **Forward planner:** state-space A* over states with an admissible heuristic (e.g. remaining people × minimum pickup+drop cost). **Backward planner:** goal regression. On the same problem both must return plans of equal cost (test); compare nodes expanded.
- **Planning graph** (SHOULD): level-by-level proposition/action layers with mutex links for small instances; show level-cost lower bound. Viewer in UI.
- **HTN** (SHOULD): methods `Evacuate(p) → [Goto(p), PickUp(p), ChooseExit, Goto(e), DropOff(p,e)]`; show the decomposition tree.
- **Execution monitor** (`monitor.py`, nondeterministic domain handling): before each action check preconditions against the live state. On violation, mark the plan invalid, record the *reason*, and replan. Only call search when invalid or when the hysteresis rule says a better target exists.
- **Partial observability** (COULD): fog-of-war mode with sensor radius `r`. Unknown cells assumed free (optimistic); replan when new hazards are sensed. Belief state shown as the set of possible fire cells. Stretch: D* Lite / LPA* vs full A* replan with measured nodes expanded.
- **Multi-agent** (COULD): 2 agents, sequential-auction task allocation on marginal cost, space-time A* with a reservation table to avoid collisions; show conflicts resolved.

### 6.8 Agent loop (`agent/loop.py`)

```
OBSERVE → REPRESENT (state→base facts) → REASON (forward chain, Bayes risk)
→ SELECT GOAL (priority / optimizer) → SEARCH → PLAN → ACT (validate then execute one action)
→ APPLY EVENTS (scripted / user / fire spread) → CHECK PLAN VALIDITY → RE-PLAN
```
- `tick()` returns a full `Snapshot{state, facts, derived, trace_delta, plan, route, metrics, replan_reason?}`.
- Event-sourced: `Session = scenario + seed + log[]`. Any tick can be rebuilt by replay. This powers the timeline scrubber.
- Failure handling: no eligible/reachable person → report "no valid plan" with the reason chain, never return an invalid route.
- **Baseline agents** (`baselines.py`) for the Module-1 benchmark: *simple reflex* (percept → action rules, no search/memory), *goal-based* (A* to nearest person), *utility-based* (full agent). `scripts/bench.py` runs all on every scenario plus N seeded random scenarios and outputs rescued %, total cost, replans, ticks.

## 7. Events

`NEW_FIRE`, `FIRE_EXTINGUISHED`, `EXIT_BLOCKED`, `EXIT_REOPENED`, `OBSTACLE_ADDED`, `OBSTACLE_REMOVED`, `FIRE_SPREAD` (automatic). Each event: apply to state → rebuild base facts → re-run inference → validate target/route/plan → replan if needed. The UI shows a before/after diff of facts and the replan reason.

## 8. API

REST (JSON, Pydantic v2 schemas, OpenAPI → TS types) plus one WebSocket.

```
POST /scenario/validate            POST /scenario            GET /scenario/{id}   GET /scenarios
POST /simulation/start             POST /simulation/step     POST /simulation/run?speed=
POST /simulation/event             POST /simulation/reset    GET  /simulation/state
GET  /simulation/replay/{tick}     # time travel
POST /search/compare               # algorithms × heuristics on one scenario
POST /search/heuristic-check
POST /kb/query                     # forward + backward + resolution
POST /bayes/infer                  # exact + approximate, with convergence data
POST /optimize/order               # hill / SA / GA vs greedy vs exhaustive
POST /adversarial/move             # minimax vs alpha-beta
POST /plan/compare                 # forward vs regression (+ graph, HTN)
POST /bench/agents                 # reflex vs goal vs utility
WS   /ws/simulation/{id}           # streams Snapshots during autoplay
```
Backend owns the authoritative state. Sessions in memory with an id; scenarios saved as JSON files; user custom scenarios saved to localStorage and exportable/importable as JSON.

## 9. Frontend specification

**Look and feel:** "mission control" dark theme, high contrast (readable on a classroom projector at 1366×768). Never rely on colour alone (distinct icons for fire, wall, person, exit, agent; patterns for Hot/rubble). Smooth animation: agent glides between cells, fire flickers, explored cells fade in as a heat gradient, route draws as an animated line, a trail shows where the agent has been.

**Layout**
- Left dock: **Scenario Builder** (palette, drag-paint, erase, undo/redo, grid size, load predefined, import/export JSON, inline validation errors highlighting offending cells).
- Centre: **Canvas** (agent, people with status badges, terrain, fire, Hot zones, exits with availability, explored set, route, plan waypoints).
- Right tabs: **Reasoning** (facts, rules fired, derived facts with provenance, "Prove it" console, proof tree) · **Search** (algorithm picker, race view, comparison table + charts, heuristic lab) · **Planning** (goal, action list with current/done/invalid, plan graph, HTN tree, forward vs backward) · **Uncertainty** (Bayes net, CPT editor, posteriors, convergence chart) · **Optimize** (order optimizer, convergence curves, adversarial mode toggle with pruning counters) · **Agent** (PEAS, environment properties, agent-type benchmark) · **Syllabus** (coverage map with "Run it" buttons).
- Bottom: controls (Start / Pause / Resume / Step / Reset / Speed), **timeline scrubber** (time travel), event injector, event log with replan reasons.

**Must-have UX**
- **Explain this decision** button on the selected target, the chosen route and every replan; opens the exact trace behind it.
- **Guided Demo mode:** one click plays the 12-step demo (Section 12), highlighting the relevant panel at each step with a short caption. Every step calls the real engine.
- **Presentation mode:** larger fonts, hides builder.
- **Command palette** (`Ctrl/Cmd+K`) and keyboard shortcuts (space = play/pause, → = step).
- Empty/error states are designed (invalid scenario, "no valid route" shown clearly and calmly).
- Export run report (JSON + printable summary of scenario, metrics, trace highlights) for the project report.

State: backend snapshot is the source of truth in a Zustand store; the builder is local until "Validate → Start".

## 10. Testing and quality

- Unit tests for every module in `tests/engine/`. Target ≥ 90% coverage on `engine/`.
- The original 10 scenarios become named integration tests (clear route, obstacles, fire avoidance, multi-person priority, blocked exit, new fire mid-run, no route, evacuation status, hazard removed, search comparison).
- **Property tests (hypothesis):**
  - A* cost == UCS cost for any consistent heuristic; BFS cost == UCS cost when all costs are equal.
  - No returned path ever contains a wall or fire cell.
  - `h` is consistent under the default cost model.
  - Alpha-beta and plain minimax pick the same move/value.
  - Forward and regression planners give equal-cost plans.
  - Forward chaining reaches a fixpoint and is idempotent; backward chaining proofs only use KB rules.
  - Approximate Bayes inference converges to exact as samples grow (statistical tolerance, seeded).
  - Replay of `scenario + seed + log` reproduces identical snapshots.
  - Exhaustive ordering ≤ every local-search result.
- **Trace-integrity e2e (Playwright):** run the Showcase scenario; assert the route/plan/metrics shown in the UI equal the engine's API response.
- Performance: A* on 30×30 under 100 ms; autoplay at 60 fps rendering on 20×20.
- `make check` is the single local gate: lint, types, tests, frontend build.

## 11. Phases and acceptance criteria

| Phase | Deliverable | Done when |
|---|---|---|
| P0 | Repo scaffold, tooling, `CLAUDE.md`, `PLAN.md`, Makefile | `make check` passes on an empty skeleton |
| P1 | World model, scenarios, validation, search (BFS, UCS, A*), fire dynamics, tests | Original tests 1–3, 7, 10 green; replay works |
| P2 | Logic KB + forward chaining, priority function, STRIPS + forward planner, agent loop, events + replanning, API + WS | Headless demo (`make demo`) runs the full original workflow from the CLI; tests 4–9 green. **This is the original plan complete.** |
| P3 | Frontend core: builder, canvas, controls, reasoning/search/planning panels, scrubber, Guided Demo | A non-developer can load a scenario, play it, inject a fire, see the replan and its reason |
| P4 (MUST extensions) | DFS/DLS/IDDFS/Greedy + race view + heuristic lab; unification + backward chaining + resolution + "Prove it"; Bayes net (exact + approximate) feeding risk; order optimizer (HC/SA/GA); adversarial fire with alpha-beta; regression planner; Agent/PEAS panel; Syllabus panel | Every MUST row in Section 3 runs from the UI and has tests |
| P5 (SHOULD) | Planning graph, HTN tree, agent-type benchmark charts, ETHICS doc | Benchmark table generated by `make bench` shows utility-based ≥ goal-based ≥ reflex on average (if not, report the real result honestly and explain why) |
| P6 | Polish, presentation mode, docs, VIVA_QA, demo script rehearsal on localhost | Section 13 checklist complete |
| P7 (COULD) | Fog-of-war + belief states, D* Lite comparison, 2-agent coordination, optional LLM narrator that *only paraphrases real traces* and is off by default | Only after P6 is done |

## 12. Demo script (build this as Guided Demo)

1. Load **Showcase**: one agent, three people, rubble, walls, spreading fire, two exits.
2. Show the state as structured data next to the grid.
3. Show facts and rules in the KB.
4. Run forward chaining; unsafe/hot zones and `AtRisk` appear with provenance.
5. Show the Bayes net posterior setting each person's risk; show exact vs approximate agreement.
6. Show priority scores with the breakdown; the far, critical person wins over the near, safe one.
7. Race BFS, DFS, UCS, Greedy, A* on the same target: real routes and metrics; A* and UCS agree on cost, DFS/Greedy do not.
8. Show the rescue-order optimizer: greedy vs SA vs GA vs exhaustive optimum.
9. Generate and show the plan (forward + regression agree; HTN tree).
10. Execute with animation. Mid-run: trigger a new fire on the route (or block exit E1).
11. Show the fact diff, the invalidated plan with its reason, and the new plan; flip to Adversarial Fire and show alpha-beta pruning savings.
12. Show the final outcome, the agent-type benchmark, and the **Impossible** scenario reporting "no valid plan".

Then: type `AtRisk(P)` into "Prove it" and show the proof tree. This is the "why should I believe this?" moment.

## 13. Definition of done

- [ ] Every MUST item in Section 3 reachable from the UI and covered by tests
- [ ] `make check` green; `make dev` brings up the full app on localhost with one command
- [ ] Trace-integrity e2e passes
- [ ] Guided Demo runs start to finish without manual fixes
- [ ] `make bench` produces real, reproducible tables (seeded)
- [ ] Docs: `README.md` (GIF/screenshots, quickstart in ≤ 3 commands), `ARCHITECTURE.md`, `SYLLABUS_MAP.md` (module → file → UI → test), `VIVA_QA.md` (≥ 25 likely questions with short answers, e.g. why is A* optimal here, why UCS ≠ BFS now, what is the closed-world assumption, why alpha-beta gives the same move, how forward and backward chaining differ, what the Bayes net conditions on), `ETHICS.md`, `DEMO_SCRIPT.md`
- [ ] No hardcoded demo results anywhere (grep for it)
- [ ] Limitations stated plainly (simulation values, not a medical triage system; no real fire detection)

## 14. Report outline (for the course submission)

1. Problem and motivation · 2. PEAS and environment analysis · 3. Architecture · 4. Each module as a section mapped to the syllabus · 5. Experiments (search comparison, heuristic lab, local search convergence, alpha-beta savings, Bayes convergence, agent-type benchmark) · 6. Replanning case studies · 7. Limitations and ethics · 8. Future work (fog, multi-agent, learning-based components).