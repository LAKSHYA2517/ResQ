"""Headless demo: the whole agent workflow on the command line. Works offline.

    uv run python scripts/demo_headless.py [--scenario showcase] [--inject-at 5] [--quiet]

Everything printed is read from engine objects; nothing here computes a result of its own.
"""

import argparse
import sys
from collections import Counter
from random import Random

from resq.agent.loop import Simulation, Snapshot, replay
from resq.decision.ordering import build_order_problem, optimise
from resq.logic.backward import prove
from resq.logic.forward import forward_chain
from resq.logic.resolution import refute
from resq.logic.rules import CORE_RULES, GEOMETRY_PREDICATES
from resq.logic.terms import atom
from resq.planning.domain import build_domain
from resq.planning.fwd_planner import plan
from resq.planning.regression import one_place_one_load, plan_backward
from resq.search import ALGORITHMS, compare
from resq.search.adversarial import FireGame, alphabeta, minimax
from resq.search.router import Router
from resq.trace import ActionExecuted, PersonStatusChanged
from resq.uncertainty.models import sensor_network
from resq.uncertainty.sampling import likelihood_weighting
from resq.world.events import EventType
from resq.world.scenarios import load_all
from resq.world.state import Exit, State, Status
from resq.world.terrain import Terrain

GLYPH = {Terrain.FLOOR: ".", Terrain.RUBBLE: "r", Terrain.WALL: "#", Terrain.EXIT: "E"}
LEGEND = (
    "A agent (@ carrying)  1-9 person  x trapped  E exit  X exit unusable\n"
    "    F fire  ~ hot  r rubble  # wall  * route"
)


def draw(snapshot: Snapshot) -> str:
    state: State = snapshot.state
    grid = [[GLYPH[t] for t in row] for row in state.terrain]
    for r, c in state.hot:
        if grid[r][c] == ".":
            grid[r][c] = "~"
    for r, c in snapshot.route[1:]:
        if grid[r][c] in ".~r":
            grid[r][c] = "*"
    for r, c in state.fire:
        grid[r][c] = "F"
    for e in state.exits:
        if not e.available:
            grid[e.pos[0]][e.pos[1]] = "X"
    for i, p in enumerate(state.people, 1):
        if p.status is Status.WAITING:
            grid[p.pos[0]][p.pos[1]] = str(i)
        elif p.status is Status.TRAPPED:
            grid[p.pos[0]][p.pos[1]] = "x"
    r, c = state.agent.pos
    grid[r][c] = "@" if state.agent.carrying else "A"
    return "\n".join("    " + " ".join(row) for row in grid)


def heading(n: int, text: str) -> None:
    print(f"\n[{n}] {text}\n" + "-" * 78)


def show_plan(snapshot: Snapshot) -> None:
    for i, step in enumerate(snapshot.memory.steps):
        mark = ">" if i == snapshot.memory.cursor else " "
        print(f"   {mark} {step.action.label:<24} cost {step.action.cost:g}")


def extras(sim: Simulation, router: Router, usable: list[Exit]) -> None:
    """The syllabus extensions on the same first tick: logic proofs, Bayes, local and
    adversarial search."""
    head, scenario = sim.head, sim.scenario
    target = head.target or ""

    print("\n    -- Prove it: one goal, three methods --")
    goal = atom("RescueNow", target)
    kb, _ = forward_chain(CORE_RULES, head.base_facts)
    proofs, steps = prove(CORE_RULES, head.base_facts, goal)
    refutation, _ = refute(CORE_RULES, head.base_facts, goal)
    print(
        f"    {goal}: forward {kb.holds(goal)}, backward {bool(proofs)} ({len(steps)} goals tried),"
        f" resolution {refutation.entailed} ({len(refutation.steps)} clauses to the empty clause)"
    )
    for step in refutation.steps:
        print(f"        {step.clause}")

    print("\n    -- Bayesian sensor network: Risk = round(5 x P(Trapped | sensors)) --")
    for b in head.beliefs:
        seen = " ".join(f"{k}={'T' if v else 'F'}" for k, v in b.evidence)
        bn = sensor_network(b.prior_fire)
        lw, _ = likelihood_weighting(bn, "Trapped", dict(b.evidence), 5000, Random(scenario.seed))
        print(
            f"    {b.person_id}: prior {b.prior_fire:.2f}  {seen}  exact {b.p_trapped:.3f}"
            f"  likelihood weighting {lw.p_true:.3f}  -> risk {b.risk}"
        )

    print("\n    -- Rescue-order optimizer (sum of weight x completion time) --")
    w = scenario.params.weights
    weights = {b.person_id: w.w_r * b.risk for b in head.beliefs}
    for p in head.state.people:
        weights[p.id] = weights.get(p.id, 0.0) + w.w_u * p.urgency
    report, _ = optimise(build_order_problem(head.state, router, weights, usable), scenario.seed)
    for row in report.rows:
        gap = "" if row.gap is None else f"  gap {row.gap:g}"
        print(f"    {row.method:<20} cost {row.cost:<8g}{gap:<10} {' -> '.join(row.order)}")

    if len(head.route) > 1:
        print("\n    -- Adversarial fire: minimax vs alpha-beta, depth 4 --")
        costs = scenario.params.cost_model
        full, _ = minimax((g := FireGame(head.state, head.route[-1], costs)), g.root(), 4)
        pruned, _ = alphabeta((g := FireGame(head.state, head.route[-1], costs)), g.root(), 4)
        print(
            f"    minimax: step {full.move}, value {full.value:g}, {full.nodes} nodes;"
            f" alpha-beta: step {pruned.move}, value {pruned.value:g}, {pruned.nodes} nodes"
            f" (same move: {full.move == pruned.move})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", default="showcase")
    parser.add_argument(
        "--inject-at", type=int, default=5, help="tick to light a fire on the route"
    )
    parser.add_argument("--quiet", action="store_true", help="skip the per-tick log")
    args = parser.parse_args()
    scenarios = load_all()
    scenario = scenarios[args.scenario]
    sim = Simulation(scenario)
    head = sim.head

    heading(
        1, f"Scenario: {scenario.name}  (seed {scenario.seed}, p_spread {scenario.params.p_spread})"
    )
    print(draw(head), f"\n    {LEGEND}", sep="\n")
    for i, p in enumerate(head.state.people, 1):
        print(
            f"    person {i} = {p.id} at {p.pos}  risk {p.risk}  urgency {p.urgency}"
            f"  {p.status.value}"
        )

    heading(2, "Knowledge base: base facts built from the state")
    counts = Counter(f.pred for f in head.base_facts)
    print("    " + "  ".join(f"{pred}×{n}" for pred, n in sorted(counts.items())))
    print("    " + ", ".join(str(f) for f in head.base_facts if f.pred not in GEOMETRY_PREDICATES))

    heading(3, f"Forward chaining with {len(CORE_RULES)} Horn rules (closed world)")
    for d in head.derived:
        if d.fact.pred not in ("Hot", "Unsafe"):
            premises = " & ".join(map(str, d.premises))
            print(f"    pass {d.iteration}  {d.fact!s:<16} <= {premises}   [{d.rule}]")
    derived = Counter(d.fact.pred for d in head.derived)
    print("    derived: " + "  ".join(f"{pred}×{n}" for pred, n in sorted(derived.items())))
    print(f"    fixpoint after {head.metrics.kb_iterations} passes")

    heading(4, "Priority = w_r·Risk + w_u·Urgency − w_d·PathCost(A*)   (simulation values)")
    for score in head.priorities:
        print(f"    {score.breakdown}")
    print(f"    target: {head.target}")

    if head.target is not None:
        heading(5, f"Search comparison: agent {head.state.agent.pos} -> {head.target}")
        router = Router(head.state, scenario.params.cost_model)
        problem = router.problem.retarget(
            head.state.agent.pos, {head.state.person(head.target).pos}
        )
        print(
            f"    {'algorithm':<32}{'cost':>6}{'steps':>7}{'expanded':>10}{'generated':>11}"
            f"{'max frontier':>14}  optimal"
        )
        for run in compare(problem, [(a, None) for a in ALGORITHMS]):
            r = run.result
            print(
                f"    {run.label:<32}{r.cost or 0:>6g}{len(r.actions):>7}{r.expanded:>10}"
                f"{r.generated:>11}{r.max_frontier:>14}  {r.optimal_vs_ucs}"
            )

        heading(6, "STRIPS plan (forward state-space A*, Travel costs from A*)")
        usable = [e for e in head.state.exits if e.available and e.pos not in head.state.fire]
        domain = build_domain(head.state, router, [head.target], usable)
        informed, _ = plan(domain.problem, domain.heuristic)
        blind, _ = plan(domain.problem)
        show_plan(head)
        print(
            f"    cost {informed.cost:g}; states expanded: {informed.expanded} with the heuristic,"
            f" {blind.expanded} without (same cost: {informed.cost == blind.cost})"
        )
        backward, _ = plan_backward(domain.problem, one_place_one_load)
        print(
            f"    regression planner: cost {backward.cost:g}, {backward.expanded} goal sets"
            f" expanded (equal to forward: {backward.cost == informed.cost})"
        )
        extras(sim, router, usable)

    heading(7, "Execution (one primitive action per tick), events and replanning")
    while not sim.head.finished and sim.head.tick < 300:
        snap = sim.step()
        if snap.tick == args.inject_at and len(snap.route) > 3:
            cell = snap.route[2]
            before = {str(f) for f in snap.base_facts} | {str(d.fact) for d in snap.derived}
            snap = sim.inject(EventType.NEW_FIRE, {"pos": list(cell)})
            after = {str(f) for f in snap.base_facts} | {str(d.fact) for d in snap.derived}
            print(f"    t{snap.tick:<3} USER EVENT NEW_FIRE at {cell}")
            print(f"         facts added: {', '.join(sorted(after - before))}")
        if snap.plan_change is not None:
            print(f"    t{snap.tick:<3} {snap.plan_change.kind.upper()}: {snap.plan_change.reason}")
            if snap.plan_change.is_replan:
                print(draw(snap))
                show_plan(snap)
        elif not args.quiet:
            for event in snap.trace:
                if isinstance(event, ActionExecuted):
                    print(f"    t{snap.tick:<3} {event.action:<8}{event.detail}")
        for event in snap.trace:
            if isinstance(event, PersonStatusChanged):
                print(f"    t{snap.tick:<3} {event.person_id}: {event.old} -> {event.new}")

    end = sim.head
    heading(8, f"Outcome: {end.status.value} at tick {end.tick}")
    print(draw(end))
    m = end.metrics
    print(
        f"    rescued {m.rescued}/{len(scenario.people)}   "
        + "  ".join(f"{p.id}:{p.status.value}" for p in end.state.people)
    )
    print(
        f"    moves {m.moves}   cost paid {m.path_cost:g}   plans {m.plans}   replans {m.replans}"
        f"   A* runs {m.searches} ({m.nodes_expanded} cells expanded)"
    )
    for reason in end.no_plan_reasons:
        print(f"    no valid plan: {reason}")
    identical = replay(scenario, tuple(sim.log), end.tick) == sim.history
    print(
        f"    replay from scenario + seed + {len(sim.log)} logged event(s) identical: {identical}"
    )

    heading(9, "Failure reporting: the Impossible scenario")
    stuck = Simulation(scenarios["impossible"]).head
    print(draw(stuck))
    print(
        f"    status: {stuck.status.value}, plan: {list(stuck.memory.steps)},"
        f" route: {list(stuck.route)}"
    )
    for reason in stuck.no_plan_reasons:
        print(f"    no valid plan: {reason}")
    return 0 if identical else 1


if __name__ == "__main__":
    sys.exit(main())
