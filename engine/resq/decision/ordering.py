"""Rescue-order optimisation: in which order should the agent evacuate everyone?

Objective (lower is better): the sum over people of ``weight * completion_time``, where the
weight is ``w_r * Risk + w_u * Urgency`` and the completion time is when that person is dropped
at their nearest reachable exit. All leg costs are real A* costs.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from itertools import permutations
from random import Random
from time import perf_counter

from ..search.local import LocalResult, Order, genetic, hill_climbing, simulated_annealing
from ..search.router import Router
from ..trace import Trace
from ..world.state import Exit, State, Status

EXHAUSTIVE_LIMIT = 7  # 7! = 5040 orders


@dataclass(frozen=True)
class OrderProblem:
    people: tuple[str, ...]
    weights: tuple[float, ...]
    exits: tuple[str, ...]  # exit chosen for each person (nearest by A* cost)
    from_start: tuple[float, ...]  # agent -> person i
    carry: tuple[float, ...]  # person i -> their exit
    between: tuple[tuple[float, ...], ...]  # exit of person i -> person j
    handling: float  # pick-up + drop-off cost per person
    skipped: tuple[str, ...]  # waiting people left out, with the reason

    def completion_times(self, order: Order) -> tuple[float, ...]:
        """When each person in ``order`` is dropped off (same positions as ``order``)."""
        t = 0.0
        out = []
        prev: int | None = None
        for i in order:
            t += self.from_start[i] if prev is None else self.between[prev][i]
            t += self.carry[i] + self.handling
            out.append(t)
            prev = i
        return tuple(out)

    def cost(self, order: Order) -> float:
        times = self.completion_times(order)
        return sum(self.weights[i] * t for i, t in zip(order, times, strict=True))

    def names(self, order: Order) -> tuple[str, ...]:
        return tuple(self.people[i] for i in order)


def build_order_problem(
    state: State, router: Router, weights: Mapping[str, float], open_exits: list[Exit]
) -> OrderProblem:
    """Cost matrix for every waiting person who can be reached and brought to an exit."""
    here = state.agent.pos
    keep: list[tuple[str, float, str, float, float]] = []  # id, weight, exit, start, carry
    skipped: list[str] = []
    cells = {}
    for p in state.people:
        if p.status is not Status.WAITING:
            continue
        to_person = router.route(here, p.pos).cost
        legs = [(c, e) for e in open_exits if (c := router.route(p.pos, e.pos).cost) is not None]
        if to_person is None:
            skipped.append(f"{p.id}: no route from the agent")
        elif not legs:
            skipped.append(f"{p.id}: no reachable open exit")
        else:
            carry, exit_ = min(legs, key=lambda x: (x[0], x[1].id))
            keep.append((p.id, weights.get(p.id, 0.0), exit_.id, to_person, carry))
            cells[p.id] = (p.pos, exit_.pos)
    between = tuple(
        tuple(
            0.0 if a == b else (router.route(cells[a][1], cells[b][0]).cost or math.inf)
            for b, *_ in keep
        )
        for a, *_ in keep
    )
    costs = router.problem.cost_model
    return OrderProblem(
        people=tuple(k[0] for k in keep),
        weights=tuple(k[1] for k in keep),
        exits=tuple(k[2] for k in keep),
        from_start=tuple(k[3] for k in keep),
        carry=tuple(k[4] for k in keep),
        between=between,
        handling=costs.pickup + costs.dropoff,
        skipped=tuple(skipped),
    )


def greedy_by_priority(problem: OrderProblem) -> Order:
    """Baseline: highest weight first (ties: nearer to the agent, then id)."""
    n = len(problem.people)
    return tuple(
        sorted(
            range(n), key=lambda i: (-problem.weights[i], problem.from_start[i], problem.people[i])
        )
    )


def exhaustive(problem: OrderProblem) -> tuple[Order, float, int] | None:
    """The true optimum by trying every order; ``None`` beyond ``EXHAUSTIVE_LIMIT`` people."""
    n = len(problem.people)
    if n > EXHAUSTIVE_LIMIT:
        return None
    best = min((problem.cost(o), o) for o in permutations(range(n)))
    return best[1], best[0], math.factorial(n)


@dataclass(frozen=True)
class OrderRow:
    method: str
    order: tuple[str, ...]
    cost: float
    evaluations: int
    curve: tuple[float, ...]
    gap: float | None  # cost - optimum; None when the optimum was not computed
    time_ms: float = field(default=0.0, compare=False)


@dataclass(frozen=True)
class OrderReport:
    problem: OrderProblem
    optimum: float | None
    rows: tuple[OrderRow, ...]


def optimise(
    problem: OrderProblem,
    seed: int,
    restarts: int = 5,
    sa_steps: int = 600,
    sa_alpha: float = 0.97,
    ga_population: int = 30,
    ga_generations: int = 60,
    ga_mutation: float = 0.2,
) -> tuple[OrderReport, Trace]:
    """Greedy and exhaustive baselines against hill climbing, annealing and a GA. Each
    stochastic method gets its own RNG derived from ``seed``."""
    n = len(problem.people)
    trace: Trace = []
    t0 = perf_counter()
    best = exhaustive(problem)
    exhaustive_ms = (perf_counter() - t0) * 1000
    optimum = best[1] if best else None
    g = greedy_by_priority(problem)
    rows: list[tuple[str, Order, float, int, tuple[float, ...], float]] = [
        ("greedy", g, problem.cost(g), 1, (problem.cost(g),), 0.0)
    ]
    runs: list[tuple[LocalResult, Trace]] = [
        hill_climbing(n, problem.cost, Random(f"{seed}:hc"), restarts),
        simulated_annealing(n, problem.cost, Random(f"{seed}:sa"), alpha=sa_alpha, steps=sa_steps),
        genetic(
            n,
            problem.cost,
            Random(f"{seed}:ga"),
            ga_population,
            ga_generations,
            mutation=ga_mutation,
        ),
    ]
    for result, t in runs:
        trace.extend(t)
        rows.append(
            (
                result.method,
                result.order,
                result.cost,
                result.evaluations,
                result.curve,
                result.time_ms,
            )
        )
    if best:
        rows.append(("exhaustive", best[0], best[1], best[2], (best[1],), exhaustive_ms))
    report = OrderReport(
        problem,
        optimum,
        tuple(
            OrderRow(
                method,
                problem.names(order),
                cost,
                evals,
                curve,
                None if optimum is None else cost - optimum,
                ms,
            )
            for method, order, cost, evals, curve, ms in rows
        ),
    )
    return report, trace
