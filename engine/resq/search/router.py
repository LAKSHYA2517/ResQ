"""A* as the low-level Travel primitive: concrete routes for the planner and the priority score."""

from ..trace import RouteComputed, Trace
from ..world.grid import Cell
from ..world.state import State
from ..world.terrain import CostModel
from .heuristics import manhattan
from .informed import astar
from .problem import GridProblem, SearchResult


class Router:
    """Routes between cells of *one* world state. Each ``(from, to)`` pair is searched at most
    once; the cache never outlives the state, so it cannot return a stale route."""

    def __init__(self, state: State, cost_model: CostModel) -> None:
        self.problem = GridProblem(state, state.agent.pos, (), cost_model)
        self._cache: dict[tuple[Cell, Cell], SearchResult[Cell]] = {}
        self.trace: Trace = []
        self.searches = 0
        self.expanded = 0
        self.time_ms = 0.0

    def route(self, src: Cell, dst: Cell) -> SearchResult[Cell]:
        key = (src, dst)
        if key not in self._cache:
            problem = self.problem.retarget(src, {dst})
            h = manhattan(problem.goals, problem.cost_model.min_step)
            result, _ = astar(problem, h, snapshots=0)
            self._cache[key] = result
            self.searches += 1
            self.expanded += result.expanded
            self.time_ms += result.time_ms
            self.trace.append(
                RouteComputed(
                    src, dst, result.found, result.cost, result.expanded, result.generated
                )
            )
        return self._cache[key]

    def step_cost(self, cell: Cell) -> float | None:
        """Live cost of entering ``cell``; ``None`` if it is impassable."""
        return self.problem.step_cost.get(cell)
