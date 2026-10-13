"""Search problem interface, grid problem, and the result record."""

from collections.abc import Callable, Collection, Hashable, Iterable, Iterator
from copy import copy
from dataclasses import dataclass
from typing import Protocol, Self

from ..world.grid import Cell, moves
from ..world.state import State
from ..world.terrain import CostModel

type Heuristic[S] = Callable[[S], float]


class Problem[S: Hashable](Protocol):
    initial: S

    def is_goal(self, state: S) -> bool: ...

    def successors(self, state: S) -> Iterable[tuple[str, S, float]]:
        """``(action, next_state, step_cost)`` in a fixed, deterministic order."""
        ...


@dataclass(frozen=True)
class SearchResult[S]:
    """Metrics are measured, never estimated.

    ``generated`` counts nodes put on the frontier including the root. ``expanded`` counts nodes
    whose successors were generated (a goal that is found is not "expanded").
    """

    algorithm: str
    found: bool
    path: tuple[S, ...]
    actions: tuple[str, ...]
    cost: float | None  # None when not found
    expanded: int
    generated: int
    max_frontier: int
    time_ms: float
    expansion_order: tuple[S, ...]
    frontier_snapshots: tuple[tuple[S, ...], ...]
    optimal_vs_ucs: bool | None = None  # filled by compare(); None = not checked
    reason: str = ""  # why the search failed


class FrontierSnapshots[S]:
    """At most ``cap`` frontier snapshots, evenly spread over the run.

    Stride doubles (and every other snapshot is dropped) whenever the cap is exceeded, so the
    memory is bounded without knowing the run length in advance. ``cap == 0`` disables it.
    """

    def __init__(self, cap: int) -> None:
        self.cap, self.stride, self.n = cap, 1, 0
        self.items: list[tuple[S, ...]] = []

    def add(self, frontier: Iterable[S]) -> None:
        if self.cap and self.n % self.stride == 0:
            self.items.append(tuple(frontier))
            if len(self.items) > self.cap:
                self.items = self.items[::2]
                self.stride *= 2
        self.n += 1


class GridProblem:
    """Shortest route over the grid. State = cell; entering a cell costs its terrain cost plus
    ``hot_extra`` if it is in the Hot zone. Walls and fire are impassable.
    """

    def __init__(
        self, state: State, start: Cell, goals: Collection[Cell], cost_model: CostModel
    ) -> None:
        self.initial: Cell = start
        self.goals = frozenset(goals)
        self.rows, self.cols = state.rows, state.cols
        self.cost_model = cost_model
        self.step_cost: dict[Cell, float] = {}
        for r in range(state.rows):
            for c in range(state.cols):
                cell = (r, c)
                base = cost_model.terrain_cost(state.terrain_at(cell))
                if base is not None and cell not in state.fire:
                    self.step_cost[cell] = base + (cost_model.hot_extra if cell in state.hot else 0)

    def retarget(self, start: Cell, goals: Collection[Cell]) -> Self:
        """Same world and costs, different endpoints (shares the step-cost table)."""
        other = copy(self)
        other.initial, other.goals = start, frozenset(goals)
        return other

    def is_goal(self, state: Cell) -> bool:
        return state in self.goals

    def successors(self, state: Cell) -> Iterator[tuple[str, Cell, float]]:
        for action, n in moves(state, self.rows, self.cols):
            cost = self.step_cost.get(n)
            if cost is not None:
                yield action, n, cost
