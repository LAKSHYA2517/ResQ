from collections import deque
from collections.abc import Hashable
from time import perf_counter

from ..trace import NodeExpanded, PathFound, SearchFailed, Trace
from .informed import best_first, reconstruct
from .problem import FrontierSnapshots, Heuristic, Problem, SearchResult


def ucs[S: Hashable](
    problem: Problem[S], heuristic: Heuristic[S] | None = None, snapshots: int = 64
) -> tuple[SearchResult[S], Trace]:
    """Uniform-cost search: best-first with h = 0. ``heuristic`` is ignored."""
    return best_first(problem, "ucs", None, snapshots)


def bfs[S: Hashable](
    problem: Problem[S], heuristic: Heuristic[S] | None = None, snapshots: int = 64
) -> tuple[SearchResult[S], Trace]:
    """Breadth-first graph search (goal test at generation, as in AIMA).

    Finds the path with the fewest *steps*; it ignores step costs, so with rubble or Hot zones
    its path cost can exceed UCS's. Successors are taken in the problem's fixed order.
    ``heuristic`` is ignored.
    """
    t0 = perf_counter()
    start = problem.initial
    g: dict[S, float] = {start: 0.0}
    parent: dict[S, tuple[S, str]] = {}
    queue: deque[S] = deque([start])
    order: list[S] = []
    trace: Trace = []
    snaps: FrontierSnapshots[S] = FrontierSnapshots(snapshots)
    generated, max_frontier = 1, 1
    goal: S | None = start if problem.is_goal(start) else None

    while queue and goal is None:
        s = queue.popleft()
        order.append(s)
        trace.append(NodeExpanded(s, g[s], 0.0, g[s], len(queue)))
        for action, n, cost in problem.successors(s):
            if n in g:
                continue
            g[n], parent[n] = g[s] + cost, (s, action)
            generated += 1
            if problem.is_goal(n):
                goal = n
                break
            queue.append(n)
        max_frontier = max(max_frontier, len(queue))
        snaps.add(queue)

    reason = "" if goal is not None else "frontier exhausted: no route to any goal"
    path, actions = reconstruct(parent, goal) if goal is not None else ((), ())
    trace.append(
        PathFound(g[goal], len(path), len(order))
        if goal is not None
        else SearchFailed(reason, len(order))
    )
    result = SearchResult(
        algorithm="bfs",
        found=goal is not None,
        path=path,
        actions=actions,
        cost=g[goal] if goal is not None else None,
        expanded=len(order),
        generated=generated,
        max_frontier=max_frontier,
        time_ms=(perf_counter() - t0) * 1000,
        expansion_order=tuple(order),
        frontier_snapshots=tuple(snaps.items),
        reason=reason,
    )
    return result, trace
