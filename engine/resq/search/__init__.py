"""Search (Module 2). One interface: ``search(problem, algorithm, heuristic, **opts)``."""

import math
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from ..trace import Trace
from ..world.grid import Cell
from .heuristics import make_heuristic
from .informed import astar
from .problem import GridProblem, Heuristic, Problem, SearchResult
from .uninformed import bfs, ucs

type Algorithm[S] = Callable[..., tuple[SearchResult[S], Trace]]

# P4 adds dfs, dls, iddfs, greedy, weighted_astar here.
ALGORITHMS: dict[str, Algorithm[Any]] = {"bfs": bfs, "ucs": ucs, "astar": astar}


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


def compare(problem: GridProblem, runs: Sequence[tuple[str, str | None]]) -> list[Run]:
    """Run each ``(algorithm, heuristic_name)`` on the same problem and mark which ones matched
    the UCS optimum. Optimality is *computed* from a reference UCS run, never asserted."""
    reference, _ = ucs(problem)
    out: list[Run] = []
    for algorithm, hname in runs:
        h = make_heuristic(hname, problem) if hname else None
        result, trace = search(problem, algorithm, h)
        if reference.cost is None:
            optimal = None
        else:
            optimal = result.cost is not None and math.isclose(result.cost, reference.cost)
        label = f"{algorithm}+{hname}" if hname else algorithm
        out.append(Run(label, algorithm, hname, replace(result, optimal_vs_ucs=optimal), trace))
    return out
