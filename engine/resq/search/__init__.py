"""Search (Module 2). One interface: ``search(problem, algorithm, heuristic, **opts)``."""

import math
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from ..trace import Trace
from ..world.grid import Cell
from .heuristics import make_heuristic
from .informed import astar, greedy, weighted_astar
from .problem import GridProblem, Heuristic, Problem, SearchResult
from .uninformed import bfs, dfs, dls, iddfs, ucs

type Algorithm[S] = Callable[..., tuple[SearchResult[S], Trace]]

ALGORITHMS: dict[str, Algorithm[Any]] = {
    "bfs": bfs,
    "dfs": dfs,
    "dls": dls,
    "iddfs": iddfs,
    "ucs": ucs,
    "greedy": greedy,
    "astar": astar,
    "weighted_astar": weighted_astar,
}
INFORMED = frozenset({"greedy", "astar", "weighted_astar"})


def search[S: Hashable](
    problem: Problem[S],
    algorithm: str,
    heuristic: Heuristic[S] | None = None,
    **opts: Any,
) -> tuple[SearchResult[S], Trace]:
    if algorithm not in ALGORITHMS:
        raise ValueError(f"unknown algorithm {algorithm!r}; choose from {sorted(ALGORITHMS)}")
    return ALGORITHMS[algorithm](problem, heuristic, **opts)


@dataclass(frozen=True)
class Run:
    label: str
    algorithm: str
    heuristic: str | None
    result: SearchResult[Cell]
    trace: Trace


def compare(
    problem: GridProblem,
    runs: Sequence[tuple[str, str | None]],
    limit: int = 20,
    w: float = 2.0,
) -> list[Run]:
    """Run each ``(algorithm, heuristic_name)`` on the same problem and mark which ones matched
    the UCS optimum. Optimality is *computed* from a reference UCS run, never asserted.

    ``limit`` is the depth limit for DLS; ``w`` the weight for weighted A* and for the
    ``weighted`` heuristic. Informed algorithms default to the Manhattan heuristic.
    """
    reference, _ = ucs(problem)
    out: list[Run] = []
    for algorithm, hname in runs:
        hname = (hname or "manhattan") if algorithm in INFORMED else None
        h = make_heuristic(hname, problem, w) if hname else None
        opts: dict[str, Any] = {}
        label = f"{algorithm}+{hname}" if hname else algorithm
        if algorithm == "dls":
            opts["limit"] = limit
            label = f"dls(limit={limit})"
        elif algorithm == "weighted_astar":
            opts["w"] = w
            label = f"weighted_astar(w={w:g})+{hname}"
        result, trace = search(problem, algorithm, h, **opts)
        if reference.cost is None:
            optimal = None
        else:
            optimal = result.cost is not None and math.isclose(result.cost, reference.cost)
        out.append(Run(label, algorithm, hname, replace(result, optimal_vs_ucs=optimal), trace))
    return out
