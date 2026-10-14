"""Best-first graph search: UCS, greedy, A* and weighted A* share this one core."""

import heapq
from collections.abc import Hashable
from itertools import count
from time import perf_counter

from ..trace import NodeExpanded, PathFound, SearchFailed, Trace
from .problem import FrontierSnapshots, Heuristic, Problem, SearchResult


def reconstruct[S: Hashable](
    parent: dict[S, tuple[S, str]], goal: S
) -> tuple[tuple[S, ...], tuple[str, ...]]:
    path, actions = [goal], []
    while path[-1] in parent:
        prev, action = parent[path[-1]]
        path.append(prev)
        actions.append(action)
    return tuple(reversed(path)), tuple(reversed(actions))


def best_first[S: Hashable](
    problem: Problem[S],
    algorithm: str,
    heuristic: Heuristic[S] | None = None,
    snapshots: int = 64,
    use_g: bool = True,
    w: float = 1.0,
) -> tuple[SearchResult[S], Trace]:
    """Expand the node with the lowest ``f = g + w*h`` (``f = h`` when ``use_g`` is False).

    Tie-breaking (deterministic): lowest f, then lowest h (prefer nodes nearer the goal), then
    first generated. A node whose g improves after being closed is re-opened, so the result is
    optimal for any *admissible* h (reopening never fires for a consistent one). Greedy
    (``use_g=False``) never re-opens: it only cares how close a node looks, not what it cost.
    """
    t0 = perf_counter()
    base: Heuristic[S] = heuristic if heuristic is not None else (lambda _s: 0.0)

    def h(state: S) -> float:
        return w * base(state)

    start = problem.initial
    tie = count()
    g: dict[S, float] = {start: 0.0}
    parent: dict[S, tuple[S, str]] = {}
    h0 = h(start)
    heap: list[tuple[float, float, int, S]] = [(h0, h0, next(tie), start)]
    frontier: dict[S, None] = {start: None}  # insertion-ordered set of live frontier nodes
    closed: set[S] = set()
    order: list[S] = []
    trace: Trace = []
    snaps: FrontierSnapshots[S] = FrontierSnapshots(snapshots)
    generated, max_frontier = 1, 1

    def result(found: bool, goal: S | None, reason: str = "") -> tuple[SearchResult[S], Trace]:
        path, actions = reconstruct(parent, goal) if goal is not None else ((), ())
        cost = g[goal] if goal is not None else None
        if goal is not None:
            trace.append(PathFound(cost or 0.0, len(path), len(order)))
        else:
            trace.append(SearchFailed(reason, len(order)))
        return (
            SearchResult(
                algorithm=algorithm,
                found=found,
                path=path,
                actions=actions,
                cost=cost,
                expanded=len(order),
                generated=generated,
                max_frontier=max_frontier,
                time_ms=(perf_counter() - t0) * 1000,
                expansion_order=tuple(order),
                frontier_snapshots=tuple(snaps.items),
                reason=reason,
            ),
            trace,
        )

    while heap:
        _, hs, _, s = heapq.heappop(heap)
        if s in closed:
            continue  # stale heap entry
        closed.add(s)
        frontier.pop(s, None)
        if problem.is_goal(s):
            return result(True, s)
        order.append(s)
        trace.append(NodeExpanded(s, g[s], hs, (g[s] if use_g else 0.0) + hs, len(frontier)))
        for action, n, cost in problem.successors(s):
            g2 = g[s] + cost
            if n in g and (not use_g or g2 >= g[n]):
                continue
            g[n], parent[n] = g2, (s, action)
            closed.discard(n)
            hn = h(n)
            heapq.heappush(heap, ((g2 if use_g else 0.0) + hn, hn, next(tie), n))
            frontier[n] = None
            generated += 1
        max_frontier = max(max_frontier, len(frontier))
        snaps.add(frontier)
    return result(False, None, "frontier exhausted: no route to any goal")


def astar[S: Hashable](
    problem: Problem[S], heuristic: Heuristic[S] | None = None, snapshots: int = 64
) -> tuple[SearchResult[S], Trace]:
    if heuristic is None:
        raise ValueError("astar needs a heuristic (use ucs for h = 0)")
    return best_first(problem, "astar", heuristic, snapshots)


def greedy[S: Hashable](
    problem: Problem[S], heuristic: Heuristic[S] | None = None, snapshots: int = 64
) -> tuple[SearchResult[S], Trace]:
    """Greedy best-first: always expand the node that *looks* closest (f = h). Fast, not optimal."""
    if heuristic is None:
        raise ValueError("greedy needs a heuristic")
    return best_first(problem, "greedy", heuristic, snapshots, use_g=False)


def weighted_astar[S: Hashable](
    problem: Problem[S],
    heuristic: Heuristic[S] | None = None,
    snapshots: int = 64,
    w: float = 2.0,
) -> tuple[SearchResult[S], Trace]:
    """f = g + w*h. For w > 1 the heuristic is inflated (inadmissible): fewer expansions, and a
    path that costs at most w times the optimum when h itself is admissible."""
    if heuristic is None:
        raise ValueError("weighted_astar needs a heuristic")
    return best_first(problem, "weighted_astar", heuristic, snapshots, w=w)
