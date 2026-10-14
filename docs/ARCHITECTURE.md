# Architecture

## Layers

```
web/  (React)  ──HTTP + WebSocket──▶  api/  (FastAPI)  ──function calls──▶  engine/resq/  (pure Python)
   renders responses                    copies results                          all AI and simulation
```

- **engine/resq** imports nothing from the web stack (a test enforces it). It can be used from
  a script, a test or the CLI demo without a server.
- **api** owns the live sessions in memory. Its Pydantic models only copy engine values; they
  may group and count, never compute a result.
- **web** never computes a route, plan, fact, probability or metric. If a number is on screen,
  an engine call produced it. The browser keeps a cache of ticks it has seen, only for the
  scrubber and the trail.

## Engine packages

| Package | Contents |
|---|---|
| `world/` | Grid geometry, terrain and cost model, immutable `State`, fire spread, events, scenario JSON and validation, the world tick (`session.py`) |
| `search/` | `Problem` protocol, `GridProblem`, eight algorithms behind `search()`, heuristics and their checker, `Router` (A* route cache for one state), local search, adversarial search |
| `logic/` | Terms and parser, unification, knowledge base, forward chaining, backward chaining, resolution, the rescue rules and base facts |
| `uncertainty/` | Bayesian networks, exact inference, sampling, the per-person sensor model |
| `planning/` | STRIPS, the grounded rescue domain, forward and regression planners, planning graph, HTN, execution monitor |
| `decision/` | Priority function with hysteresis; rescue-order optimisation |
| `agent/` | Primitive actions, the agent loop, baseline agents, the PEAS profile |
| `trace.py` | Every typed trace event |

## The agent loop

One tick, as implemented in `agent/loop.py`:

```
OBSERVE        the State at tick t
SEARCH         A* from the agent to every waiting person (reachability and real path cost)
REASON         sensors -> Bayes posterior -> Risk(P); base facts -> forward chaining -> derived facts
SELECT GOAL    rank Eligible(P) by priority; switch target only beyond the margin delta
CHECK          is the inherited plan still executable? (stored routes unblocked, STRIPS
               preconditions true in the live facts) -> replan reason if not
PLAN           STRIPS forward A* for the chosen person; Travel costs and paths from A*
ACT            validate, then execute exactly one primitive action
WORLD          fire spreads (or the adversary ignites), clock advances, events of t+1 apply
```

`deliberate()` covers OBSERVE to PLAN, `transition()` covers ACT and WORLD.

### Timeline rule

An event dated tick *t* is part of snapshot *t*. Scripted events are applied when the tick
begins. A user event injected while the run sits at tick *t* is applied to that tick and makes
the agent deliberate again (`react()`), so its plan is re-checked and any replan reason is
real. Replay applies events the same way.

### Determinism and replay

- Fire spread at tick *t* uses `Random(f"{seed}:{t}")`. Sensor noise uses an RNG keyed on
  seed, tick, person and sensor. No other randomness exists in a run.
- A session is `scenario + seed + user-event log`. `replay(scenario, log, t)` rebuilds every
  snapshot and must equal the live history. Tests check this on every scenario, on random
  event logs (property test), through the API (`/simulation/replay/{t}?fresh=true`) and in the
  run report (`replay_identical`).
- Wall-clock timings are the only non-deterministic values. They live in fields excluded from
  equality.

### When the agent replans

| Kind | Trigger |
|---|---|
| `invalid` | A remaining route cell is blocked, or a STRIPS precondition (Waiting, ExitOpen, ...) no longer holds |
| `target_switch` | Another person's priority beats the current target by more than delta |
| `cheaper` | The fire, terrain or exits changed and a strictly cheaper plan exists for the same goal |

With a static world there are no planner calls between events.

## Default values

All of these are simulation values, set per scenario under `params`.

| Cost model | Value | Meaning |
|---|---|---|
| floor | 1 | cost of entering a floor cell |
| rubble | 3 | cost of entering rubble |
| exit | 1 | cost of entering an exit cell |
| hot_extra | 4 | added when the cell is in the Hot zone (next to fire) |
| pickup, dropoff | 1 each | abstract actions, one tick each |

Walls and fire are impassable. The Manhattan heuristic is scaled by the cheapest step
(`min(floor, rubble, exit)`), which keeps it consistent under any cost model.

| Priority weights | Value |
|---|---|
| w_r (risk), w_u (urgency), w_d (path cost) | 5, 3, 1 |
| gamma (urgency per tick waiting), urgency cap | 0.1, 5 |
| Urgent(P) threshold | 3 |
| delta (hysteresis margin) | 2 |

| Sensor network (per person) | P(true \| parent true) | P(true \| parent false) |
|---|---|---|
| Fire (prior) | risk / 5, clamped to [0.05, 0.95] | |
| Smoke given Fire | 0.7 | 0.3 |
| Heat given Fire | 0.6 | 0.2 |
| Trapped given Fire | 0.8 | 0.05 |
| Voice given Trapped | 0.6 | 0.2 |

Simulated readings: smoke if fire is within 2 cells; heat and voice if the person's cell is Hot
or burning. `Risk(P) = round(5 × P(Trapped | readings))`.

## Knowledge base

Closed-world assumption, Horn clauses, no negation in rules. Base facts are rebuilt from the
state every tick and derived facts are recomputed from scratch, so no stale fact can survive.
`Reachable(P)` (from A*) and `Urgent(P)` (from arithmetic) enter as base facts, because Horn
clauses over symbols cannot search or compute. "An exit is open" is asked as a query: absence
of `Unavailable(e)`.

```
fire_unsafe:   Fire(X) -> Unsafe(X)
hot_zone:      Adjacent(X, Y) & Fire(Y) -> Hot(X)
hot_unsafe:    Hot(X) -> Unsafe(X)
at_risk:       Person(P, X) & Unsafe(X) -> AtRisk(P)
trapped:       Person(P, X) & Fire(X) -> Trapped(P)
exit_on_fire:  Exit(E, X) & Fire(X) -> Unavailable(E)
exit_blocked:  Exit(E, X) & Blocked(X) -> Unavailable(E)
eligible:      Waiting(P) & Reachable(P) -> Eligible(P)
critical:      AtRisk(P) & Urgent(P) -> Critical(P)
rescue_now:    Eligible(P) & Critical(P) -> RescueNow(P)
```

## Search conventions

- Successors are generated up, down, left, right. Best-first ties break on lowest f, then
  lowest h, then first generated.
- BFS tests the goal when a node is generated (AIMA); UCS and A* when it is expanded. A closed
  node is re-opened if its cost improves, so A* is optimal for any admissible heuristic.
- DLS and IDDFS use a depth-stamped explored set: a cell is expanded again only when reached at
  a shallower depth.
- "Optimal" in any table is computed against a reference UCS run, never assumed.

## API

| Area | Endpoints |
|---|---|
| Scenarios | `GET /scenarios`, `GET /scenario/{id}`, `POST /scenario/validate`, `POST /scenario` |
| Simulation | `POST /simulation/start · step · run · event · reset`, `GET /simulation/state · log · report`, `GET /simulation/replay/{tick}` |
| Analysis | `POST /search/compare · heuristic-check`, `POST /kb/query`, `GET /kb/rules`, `GET /bayes/network`, `POST /bayes/infer`, `POST /optimize/order`, `POST /adversarial/move`, `POST /plan/compare · graph · htn`, `GET /agent/profile`, `POST /bench/agents` |
| Stream | `WS /ws/simulation/{id}` |

The interactive schema is at <http://localhost:8000/docs> while `make dev` runs.

## Testing

| Layer | Where | What |
|---|---|---|
| Engine | `tests/engine/` | Unit and property tests (hypothesis): A* = UCS for consistent heuristics, BFS = UCS on uniform costs, no path through walls or fire, alpha-beta = minimax, forward = regression plan cost, forward/backward/resolution agree, sampling converges, exhaustive ≤ local search, replay reproduces snapshots, plus the original ten integration tests |
| API | `tests/api/` | Every endpoint checked against a direct engine call |
| Web | `web/src/**/*.test.ts(x)` | Stores, draft operations, panels rendered from real engine snapshots |
| Browser | `tests/e2e/` | Acceptance flows, every syllabus row from the UI, the full guided demo, and a trace-integrity run comparing the screen with the engine at every tick |

Engine coverage is about 99%. Each phase also ran mutation spot-checks (deliberately breaking
logic to confirm the tests notice). Measured performance: A* on 30×30 well under the 100 ms
target, about 9 ms per agent tick on a 30×30 grid, and 60 fps while autoplaying a 20×20 grid
(headless Chromium).
