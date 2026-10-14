"""Local search over permutations: hill climbing, simulated annealing, genetic algorithm.

Each minimises ``cost(order)`` where ``order`` is a permutation of ``range(n)``, and returns its
convergence curve (best cost so far per iteration or generation). All randomness comes from the
``Random`` passed in, so a seed reproduces a run exactly.
"""

import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from random import Random
from time import perf_counter

from ..trace import OptimizerDone, Trace

type Order = tuple[int, ...]
type Cost = Callable[[Order], float]


@dataclass(frozen=True)
class LocalResult:
    method: str
    order: Order
    cost: float
    evaluations: int  # calls to the cost function
    curve: tuple[float, ...]  # best cost so far, one point per iteration / generation
    time_ms: float = field(default=0.0, compare=False)


class _Counted:
    def __init__(self, cost: Cost) -> None:
        self.cost, self.calls = cost, 0

    def __call__(self, order: Order) -> float:
        self.calls += 1
        return self.cost(order)


def neighbours(order: Order) -> Iterator[Order]:
    """Every order one swap or one insertion away (fixed enumeration order)."""
    n = len(order)
    for i in range(n):
        for j in range(i + 1, n):
            swapped = list(order)
            swapped[i], swapped[j] = swapped[j], swapped[i]
            yield tuple(swapped)
    for i in range(n):
        for j in range(n):
            if abs(i - j) > 1:  # moving one place is an adjacent swap, already listed
                moved = list(order)
                moved.insert(j, moved.pop(i))
                yield tuple(moved)


def _done(
    method: str, order: Order, cost: float, f: _Counted, curve: list[float], t0: float
) -> tuple[LocalResult, Trace]:
    result = LocalResult(method, order, cost, f.calls, tuple(curve), (perf_counter() - t0) * 1000)
    return result, [OptimizerDone(method, order, cost, f.calls)]


def hill_climbing(
    n: int, cost: Cost, rng: Random, restarts: int = 5, max_steps: int = 200
) -> tuple[LocalResult, Trace]:
    """Steepest descent: move to the best neighbour until none is better, then restart from a
    random order. Restarts are the only way out of a local optimum."""
    t0 = perf_counter()
    f = _Counted(cost)
    best: Order = tuple(range(n))
    best_cost = f(best)
    curve = [best_cost]
    for r in range(max(1, restarts)):
        current = best if r == 0 else tuple(rng.sample(range(n), n))
        current_cost = best_cost if r == 0 else f(current)
        for _ in range(max_steps):
            step = min(((f(c), c) for c in neighbours(current)), default=None)
            if step is None or step[0] >= current_cost:
                break  # local optimum
            current_cost, current = step
            if current_cost < best_cost:
                best, best_cost = current, current_cost
            curve.append(best_cost)
        if current_cost < best_cost:
            best, best_cost = current, current_cost
        curve.append(best_cost)
    return _done("hill_climbing", best, best_cost, f, curve, t0)


def simulated_annealing(
    n: int,
    cost: Cost,
    rng: Random,
    t0: float | None = None,
    alpha: float = 0.97,
    steps: int = 600,
) -> tuple[LocalResult, Trace]:
    """Random swap each step; always accept improvements, accept a worsening of d with
    probability exp(-d / T). T cools geometrically (T <- alpha * T), so early on it explores
    and later it behaves like hill climbing."""
    start_time = perf_counter()
    f = _Counted(cost)
    current: Order = tuple(range(n))
    current_cost = f(current)
    best, best_cost = current, current_cost
    curve = [best_cost]
    temperature = t0 if t0 is not None else max(1.0, 0.2 * abs(current_cost))
    for _ in range(steps if n > 1 else 0):
        i, j = rng.sample(range(n), 2)
        candidate = list(current)
        candidate[i], candidate[j] = candidate[j], candidate[i]
        c = f(tuple(candidate))
        delta = c - current_cost
        if delta <= 0 or rng.random() < math.exp(-delta / temperature):
            current, current_cost = tuple(candidate), c
            if c < best_cost:
                best, best_cost = current, c
        temperature = max(1e-9, temperature * alpha)
        curve.append(best_cost)
    return _done("simulated_annealing", best, best_cost, f, curve, start_time)


def order_crossover(a: Order, b: Order, rng: Random) -> Order:
    """OX: keep a slice of parent ``a`` in place, fill the rest in the order it appears in ``b``."""
    n = len(a)
    i, j = sorted(rng.sample(range(n + 1), 2))
    kept = set(a[i:j])
    rest = iter(x for x in b if x not in kept)
    return tuple(a[k] if i <= k < j else next(rest) for k in range(n))


def genetic(
    n: int,
    cost: Cost,
    rng: Random,
    population: int = 30,
    generations: int = 60,
    tournament: int = 3,
    mutation: float = 0.2,
) -> tuple[LocalResult, Trace]:
    """Tournament selection, order crossover, swap mutation, and one elite carried over."""
    t0 = perf_counter()
    f = _Counted(cost)
    identity: Order = tuple(range(n))
    pool = [identity] + [tuple(rng.sample(range(n), n)) for _ in range(max(1, population) - 1)]
    scored = sorted((f(o), o) for o in pool)
    curve = [scored[0][0]]

    def pick() -> Order:
        return min(rng.sample(scored, min(tournament, len(scored))))[1]

    for _ in range(generations if n > 1 else 0):
        children = [scored[0][1]]  # elitism: the best survives unchanged
        while len(children) < len(scored):
            child = list(order_crossover(pick(), pick(), rng))
            if rng.random() < mutation:
                i, j = rng.sample(range(n), 2)
                child[i], child[j] = child[j], child[i]
            children.append(tuple(child))
        scored = sorted((f(o), o) for o in children)
        curve.append(scored[0][0])
    return _done("genetic", scored[0][1], scored[0][0], f, curve, t0)
