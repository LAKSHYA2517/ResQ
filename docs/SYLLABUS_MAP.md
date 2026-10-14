# Syllabus map (BCSE306L)

Each syllabus topic, where it lives in the code, where to see it in the app, and the tests that
check it. Engine paths are under `engine/resq/`. "Run it" buttons in the app's **Syllabus** tab
jump straight to each feature.

## Module 1: Introduction to AI and intelligent agents

| Topic | Code | In the app | Tests |
|---|---|---|---|
| Agents, PEAS | `agent/profile.py` (`PEAS`, `AGENT_TYPE`) | Agent tab | `tests/api/test_p4.py::test_agent_profile_follows_the_scenario` |
| Environment properties | `agent/profile.py::environment` (derived from scenario parameters) | Agent tab; changes with fire spread, sensor noise, worst-case fire | same |
| Structure of agents | `agent/loop.py` (observe, reason, plan, act cycle) | Every tick; event log | `tests/engine/test_agent.py` |
| Agent types: reflex, goal-based, utility-based | `agent/baselines.py` | Agent tab → Run benchmark; `make bench` → `docs/BENCHMARK.md` | `tests/engine/test_p5.py` (benchmark, reflex vs wall, triage) |

## Module 2: Problem solving by search

| Topic | Code | In the app | Tests |
|---|---|---|---|
| State space, problem formulation | `search/problem.py` (`Problem`, `GridProblem`) | Search tab | `tests/engine/test_search.py` |
| BFS, UCS, DFS, DLS, IDDFS | `search/uninformed.py` | Search tab → Run comparison / Race | `test_search.py` (original tests 1, 2, 3, 7, 10; DLS cutoff; IDDFS = BFS steps; property tests) |
| Greedy best-first, A*, weighted A* | `search/informed.py` | Search tab | `test_search.py::test_dfs_and_greedy_are_honestly_non_optimal`, `test_weighted_astar_trades_cost_for_speed_within_its_bound`, A* = UCS property test |
| Heuristics, admissibility, consistency | `search/heuristics.py` (`check_heuristic`) | Search tab → Heuristic lab | `test_search.py` heuristic tests; `tests/api/test_p4.py::test_heuristic_check` |
| Comparing algorithms | `search/__init__.py::compare` (optimality computed against UCS) | Comparison table, Algorithm Race | `tests/e2e/p4.spec.ts` Module 2 |

## Module 3: Local search and adversarial search

| Topic | Code | In the app | Tests |
|---|---|---|---|
| Hill climbing (restarts), simulated annealing, genetic algorithm | `search/local.py` | Optimize tab → rescue-order optimiser | `tests/engine/test_optimize_adversarial.py` (no method beats exhaustive, seeded, local optimum reached) |
| Optimisation problem | `decision/ordering.py` (Σ weight × completion time, exhaustive optimum for ≤ 7) | Optimize tab (load Mass Evacuation for 7 people) | same; `tests/api/test_p4.py::test_optimize_order` |
| Game trees, minimax | `search/adversarial.py::minimax`, `FireGame` | Optimize tab → Analyse this move | AIMA figure 5.2 tree test; random-tree property test |
| Alpha-beta pruning | `search/adversarial.py::alphabeta` | Same panel: nodes saved, same move | `test_prop_alphabeta_matches_minimax_value_and_move`, `test_fire_game_same_move_fewer_nodes` |
| Adversarial environment | `agent/loop.py::_adversarial_tick` | Optimize tab → Restart with worst-case fire | `tests/engine/test_agent.py::test_adversarial_fire_is_worse_than_chance_and_replays` |

## Module 4: Logic and reasoning

| Topic | Code | In the app | Tests |
|---|---|---|---|
| Propositional and first-order syntax | `logic/terms.py` (terms, atoms, Horn rules, parser) | Logic tab → rules list | `tests/engine/test_logic.py` |
| Unification | `logic/unify.py` (MGU with occurs check) | Behind every proof | `test_logic.py` unification tests and property tests |
| Knowledge base, closed world | `logic/kb.py`, `logic/rules.py` | Logic tab → base facts, rules | `test_logic.py::test_core_rules_on_a_state` |
| Forward chaining | `logic/forward.py` (fixpoint, provenance) | Logic tab → derived facts by pass | `test_logic.py` (fixpoint, idempotent, provenance) |
| Backward chaining | `logic/backward.py` (SLD, proof trees) | Logic tab → Prove it | `tests/engine/test_logic_proofs.py` |
| Resolution | `logic/resolution.py` (CNF, binary resolution, refutation) | Prove it → step-by-step to the empty clause | `test_logic_proofs.py` (three methods agree on every scenario) |

## Module 5: Uncertain knowledge and reasoning

| Topic | Code | In the app | Tests |
|---|---|---|---|
| Bayes' rule, Bayesian networks | `uncertainty/bayesnet.py`, `uncertainty/models.py` | Bayes tab → beliefs, network diagram, editable tables | `tests/engine/test_uncertainty.py` |
| Exact inference | `uncertainty/exact.py` (enumeration, variable elimination) | Bayes tab → Infer | AIMA burglary network (0.284); enumeration = elimination property test |
| Approximate inference | `uncertainty/sampling.py` (rejection, likelihood weighting, Gibbs) | Convergence chart of error against samples | `test_sampling_converges_to_the_exact_posterior` |
| Decisions under uncertainty | `agent/loop.py`: Risk(P) = round(5 × P(Trapped \| sensors)) feeds the priority | Bayes tab; Plan tab priority breakdown | `test_agent.py::test_risk_in_the_priority_is_the_bayes_posterior` |

## Module 6: Planning

| Topic | Code | In the app | Tests |
|---|---|---|---|
| Classical planning, STRIPS | `planning/strips.py`, `planning/domain.py` | Plan tab → plan steps | `tests/engine/test_planning.py` |
| Forward state-space search | `planning/fwd_planner.py` (A*, admissible heuristic) | Plan tab | heuristic admissibility property test |
| Backward (regression) search | `planning/regression.py` | Plan tab → Compare planners | forward = regression cost property test |
| Planning graphs | `planning/planning_graph.py` (mutexes, level bound) | Plan tab → Build graph | `tests/engine/test_p5.py` (each mutex kind, goal level ≤ plan length) |
| Hierarchical planning | `planning/htn.py` | Plan tab → Decompose | `test_p5.py` HTN tests |
| Nondeterministic domains, execution monitoring | `planning/monitor.py`, `agent/loop.py` | Inject an event → the replan card | `test_agent.py` original tests 5, 6, 9; `tests/e2e/flow.spec.ts` |
| Multi-agent planning, sensorless planning | not built (optional tier) | | |

## Module 7: Communicating, perceiving and acting

Out of scope. The agent's "perception" is a set of simulated sensor readings fed to the
Bayesian network (`uncertainty/models.py::read_sensors`).

## Module 8: Contemporary issues

| Topic | Where |
|---|---|
| Ethics of automated triage, limits of classical AI | [ETHICS.md](ETHICS.md) |
