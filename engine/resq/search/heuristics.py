"""Grid heuristics and a checker that *computes* admissibility and consistency."""

import heapq
import math
from dataclasses import dataclass

from ..world.grid import Cell, moves
from .problem import GridProblem, Heuristic

EPS = 1e-9
MAX_REPORTED = 25


def manhattan(goals: frozenset[Cell], min_step: float) -> Heuristic[Cell]:
    """Manhattan distance to the nearest goal x cheapest step: consistent under any cost model
    in which every step costs at least ``min_step`` (|dh| <= min_step <= c(n, n'))."""

    def h(cell: Cell) -> float:
        return min(abs(cell[0] - r) + abs(cell[1] - c) for r, c in goals) * min_step

    return h


def euclidean(goals: frozenset[Cell], min_step: float) -> Heuristic[Cell]:
    def h(cell: Cell) -> float:
        return min(math.hypot(cell[0] - r, cell[1] - c) for r, c in goals) * min_step

    return h


def zero() -> Heuristic[Cell]:
    return lambda _cell: 0.0


def weighted(h: Heuristic[Cell], w: float) -> Heuristic[Cell]:
    """``w * h``: inadmissible for w > 1 (faster, but may return a costlier path)."""
    return lambda cell: w * h(cell)


HEURISTICS = ("manhattan", "euclidean", "zero", "weighted")


def make_heuristic(name: str, problem: GridProblem, w: float = 2.0) -> Heuristic[Cell]:
    min_step = problem.cost_model.min_step
    match name:
        case "manhattan":
            return manhattan(problem.goals, min_step)
        case "euclidean":
            return euclidean(problem.goals, min_step)
        case "zero":
            return zero()
        case "weighted":
            return weighted(manhattan(problem.goals, min_step), w)
    raise ValueError(f"unknown heuristic {name!r}; choose from {HEURISTICS}")


@dataclass(frozen=True)
class HeuristicCheck:
    admissible: bool
    consistent: bool
    # (cell, h, true_cost_to_goal)
    admissibility_violations: tuple[tuple[Cell, float, float], ...]
    # (cell, next_cell, h(cell), step_cost, h(next_cell))
    consistency_violations: tuple[tuple[Cell, Cell, float, float, float], ...]
    n_admissibility_violations: int
    n_consistency_violations: int


def true_costs(problem: GridProblem) -> dict[Cell, float]:
    """Exact cost-to-goal for every cell that can reach a goal (reverse Dijkstra)."""
    dist: dict[Cell, float] = {}
    heap = [(0.0, g) for g in sorted(problem.goals) if g in problem.step_cost]
    heapq.heapify(heap)
    while heap:
        d, cell = heapq.heappop(heap)
        if cell in dist:
            continue
        dist[cell] = d
        for _, prev in moves(cell, problem.rows, problem.cols):
            if prev in problem.step_cost and prev not in dist:
                # edge prev -> cell costs step_cost[cell] (cost of entering `cell`)
                heapq.heappush(heap, (d + problem.step_cost[cell], prev))
    return dist


def check_heuristic(problem: GridProblem, h: Heuristic[Cell]) -> HeuristicCheck:
    """Exhaustively test h(n) <= h*(n) (admissible) and h(n) <= c(n,n') + h(n') (consistent)
    over every passable cell. Violation lists are capped; the counts are exact."""
    dist = true_costs(problem)
    adm: list[tuple[Cell, float, float]] = []
    n_adm = n_con = 0
    con: list[tuple[Cell, Cell, float, float, float]] = []
    for cell in sorted(problem.step_cost):
        hc = h(cell)
        if cell in dist and hc > dist[cell] + EPS:
            n_adm += 1
            if len(adm) < MAX_REPORTED:
                adm.append((cell, hc, dist[cell]))
        for _, n, cost in problem.successors(cell):
            hn = h(n)
            if hc > cost + hn + EPS:
                n_con += 1
                if len(con) < MAX_REPORTED:
                    con.append((cell, n, hc, cost, hn))
    return HeuristicCheck(n_adm == 0, n_con == 0, tuple(adm), tuple(con), n_adm, n_con)
