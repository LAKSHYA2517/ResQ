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


def _depth_limited[S: Hashable](
    problem: Problem[S], limit: int, order: list[S], trace: Trace, snaps: FrontierSnapshots[S]
) -> tuple[S | None, dict[S, tuple[S, str]], dict[S, float], bool, int, int]:
    """One depth-limited DFS pass. Returns (goal, parents, g, cutoff, generated, max_frontier).

    Graph search with a *depth-stamped* explored set: a state is expanded again only if it is
    reached at a strictly shallower depth than before. A plain explored set would make iterative
    deepening incomplete (a node first met deep down would block the shallow route to it), and
    checking only the current path would blow up exponentially on an open grid.
    """
    start = problem.initial
    parent: dict[S, tuple[S, str]] = {}
    g: dict[S, float] = {start: 0.0}
    best_depth: dict[S, int] = {start: 0}
    stack: list[tuple[S, int]] = [(start, 0)]
    cutoff = False
    generated, max_frontier = 1, 1
    while stack:
        s, depth = stack.pop()
        if best_depth[s] < depth:
            continue  # a shallower visit already superseded this entry
        if problem.is_goal(s):
            return s, parent, g, cutoff, generated, max_frontier
        if depth == limit:
            cutoff = True
            continue
        order.append(s)
        trace.append(NodeExpanded(s, g[s], 0.0, g[s], len(stack)))
        # reversed, so the first successor in the problem's order is expanded first
        for action, n, cost in reversed(list(problem.successors(s))):
            if n in best_depth and best_depth[n] <= depth + 1:
                continue
            best_depth[n] = depth + 1
            g[n], parent[n] = g[s] + cost, (s, action)
            stack.append((n, depth + 1))
            generated += 1
        max_frontier = max(max_frontier, len(stack))
        snaps.add(s for s, _ in stack)
    return None, parent, g, cutoff, generated, max_frontier


def _dfs_result[S: Hashable](
    algorithm: str,
    t0: float,
    goal: S | None,
    parent: dict[S, tuple[S, str]],
    g: dict[S, float],
    reason: str,
    order: list[S],
    trace: Trace,
    snaps: FrontierSnapshots[S],
    generated: int,
    max_frontier: int,
    limit: int | None,
) -> tuple[SearchResult[S], Trace]:
    path, actions = reconstruct(parent, goal) if goal is not None else ((), ())
    trace.append(
        PathFound(g[goal], len(path), len(order))
        if goal is not None
        else SearchFailed(reason, len(order))
    )
    result = SearchResult(
        algorithm=algorithm,
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
        reason="" if goal is not None else reason,
        depth_limit=limit,
    )
    return result, trace


def dls[S: Hashable](
    problem: Problem[S],
    heuristic: Heuristic[S] | None = None,
    snapshots: int = 64,
    limit: int = 20,
) -> tuple[SearchResult[S], Trace]:
    """Depth-limited search: DFS that never goes deeper than ``limit`` steps. Not optimal, and
    not complete when the limit is too small (the result then says "cutoff", not "no route")."""
    t0 = perf_counter()
    order: list[S] = []
    trace: Trace = []
    snaps: FrontierSnapshots[S] = FrontierSnapshots(snapshots)
    goal, parent, g, cutoff, generated, max_frontier = _depth_limited(
        problem, limit, order, trace, snaps
    )
    reason = (
        f"cutoff: no goal within depth limit {limit}"
        if cutoff
        else "search space exhausted: no route to any goal"
    )
    return _dfs_result(
        "dls", t0, goal, parent, g, reason, order, trace, snaps, generated, max_frontier, limit
    )


def dfs[S: Hashable](
    problem: Problem[S], heuristic: Heuristic[S] | None = None, snapshots: int = 64
) -> tuple[SearchResult[S], Trace]:
    """Depth-first graph search: follows the first successor as deep as it goes. Complete on a
    finite graph, but the path it returns is usually far from the cheapest."""
    t0 = perf_counter()
    start = problem.initial
    parent: dict[S, tuple[S, str]] = {}
    g: dict[S, float] = {start: 0.0}
    explored: set[S] = set()
    stack: list[S] = [start]
    order: list[S] = []
    trace: Trace = []
    snaps: FrontierSnapshots[S] = FrontierSnapshots(snapshots)
    generated, max_frontier = 1, 1
    goal: S | None = None
    while stack:
        s = stack.pop()
        if s in explored:
            continue
        explored.add(s)
        if problem.is_goal(s):
            goal = s
            break
        order.append(s)
        trace.append(NodeExpanded(s, g[s], 0.0, g[s], len(stack)))
        for action, n, cost in reversed(list(problem.successors(s))):
            if n in explored:
                continue
            g[n], parent[n] = g[s] + cost, (s, action)  # the latest push is the one popped
            stack.append(n)
            generated += 1
        max_frontier = max(max_frontier, len(stack))
        snaps.add(stack)
    reason = "search space exhausted: no route to any goal"
    return _dfs_result(
        "dfs", t0, goal, parent, g, reason, order, trace, snaps, generated, max_frontier, None
    )


def iddfs[S: Hashable](
    problem: Problem[S],
    heuristic: Heuristic[S] | None = None,
    snapshots: int = 64,
    max_depth: int = 1000,
) -> tuple[SearchResult[S], Trace]:
    """Iterative deepening: DLS with limit 0, 1, 2, ... until a goal is found or a pass ends
    without hitting its limit. Finds a path with the fewest steps (like BFS) using DFS memory;
    ``expanded`` counts the repeated work of every pass."""
    t0 = perf_counter()
    order: list[S] = []
    trace: Trace = []
    snaps: FrontierSnapshots[S] = FrontierSnapshots(snapshots)
    generated = max_frontier = 0
    goal: S | None = None
    parent: dict[S, tuple[S, str]] = {}
    g: dict[S, float] = {}
    limit = 0
    reason = f"no goal within max depth {max_depth}"
    for limit in range(max_depth + 1):
        goal, parent, g, cutoff, gen, front = _depth_limited(problem, limit, order, trace, snaps)
        generated += gen
        max_frontier = max(max_frontier, front)
        if goal is not None:
            break
        if not cutoff:
            reason = "search space exhausted: no route to any goal"
            break
    return _dfs_result(
        "iddfs", t0, goal, parent, g, reason, order, trace, snaps, generated, max_frontier, limit
    )
