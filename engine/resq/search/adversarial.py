"""Adversarial search: depth-limited minimax, with and without alpha-beta pruning.

The fire game is two-player and zero-sum. The agent (MIN) wants to finish its current leg as
cheaply as possible; the fire (MAX) ignites cells to make that as expensive as possible, ideally
cutting the agent off (infinite cost). Players alternate.
"""

import math
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field, replace
from itertools import combinations
from time import perf_counter
from typing import Protocol

from ..trace import GameSearched, Trace
from ..world.grid import Cell, moves
from ..world.state import State
from ..world.terrain import CostModel, Terrain
from .heuristics import manhattan
from .informed import astar
from .problem import GridProblem


class Game[S: Hashable, M](Protocol):
    def is_max(self, state: S) -> bool: ...

    def moves(self, state: S) -> Sequence[M]:
        """Legal moves in a fixed order (it decides ties, so it must be deterministic)."""
        ...

    def result(self, state: S, move: M) -> S: ...

    def terminal(self, state: S) -> bool: ...

    def evaluate(self, state: S) -> float:
        """Value of a terminal or depth-limit state, from MAX's point of view."""
        ...


@dataclass(frozen=True)
class Decision[M]:
    algorithm: str
    move: M | None  # None when the root has no legal move
    value: float  # math.inf = MIN is cut off
    nodes: int  # states visited
    cutoffs: int  # subtrees pruned (always 0 for plain minimax)
    line: tuple[M, ...]  # principal variation: best play for both sides from the root
    time_ms: float = field(default=0.0, compare=False)


def _search[S: Hashable, M](
    game: Game[S, M], root: S, depth: int, prune: bool
) -> tuple[Decision[M], Trace]:
    t0 = perf_counter()
    nodes = cutoffs = 0

    def value(state: S, d: int, alpha: float, beta: float) -> tuple[float, tuple[M, ...]]:
        nonlocal nodes, cutoffs
        nodes += 1
        if d == 0 or game.terminal(state):
            return game.evaluate(state), ()
        options = game.moves(state)
        if not options:
            return game.evaluate(state), ()
        maximising = game.is_max(state)
        best = -math.inf if maximising else math.inf
        line: tuple[M, ...] = ()
        first = True
        for i, move in enumerate(options):
            v, rest = value(game.result(state, move), d - 1, alpha, beta)
            # strict comparison: among equal moves the first in the fixed order wins, which is
            # what makes minimax and alpha-beta choose the same move, not just the same value
            if first or (v > best if maximising else v < best):
                best, line, first = v, (move, *rest), False
            if prune:
                if maximising:
                    alpha = max(alpha, best)
                else:
                    beta = min(beta, best)
                if alpha >= beta:
                    cutoffs += len(options) - i - 1
                    break
        return best, line

    best, line = value(root, depth, -math.inf, math.inf)
    name = "alphabeta" if prune else "minimax"
    decision = Decision(
        name, line[0] if line else None, best, nodes, cutoffs, line, (perf_counter() - t0) * 1000
    )
    shown = None if math.isinf(best) else best
    return decision, [GameSearched(name, depth, shown, nodes, cutoffs)]


def minimax[S: Hashable, M](game: Game[S, M], root: S, depth: int) -> tuple[Decision[M], Trace]:
    """Exhaustive depth-limited minimax."""
    return _search(game, root, depth, prune=False)


def alphabeta[S: Hashable, M](game: Game[S, M], root: S, depth: int) -> tuple[Decision[M], Trace]:
    """Minimax with alpha-beta pruning: same value and same move, fewer states visited."""
    return _search(game, root, depth, prune=True)


# --- the fire game --------------------------------------------------------------------------------

type FireState = tuple[Cell, frozenset[Cell], float, bool]  # agent, fire, cost so far, fire to move
type FireMove = tuple[Cell, ...]  # agent: the one cell it steps to; fire: the cells it ignites


class FireGame:
    """Agent (MIN) walks towards ``goal``; fire (MAX) ignites up to ``k`` frontier cells a turn.

    Leaf value = cost paid so far + the A* cost of finishing the leg in that fire layout
    (infinite if no route is left). The fire attacks the *route*: it may not ignite the agent's
    cell or the destination itself, otherwise every game next to a fire would be decided in one
    move. To keep the tree small it only considers the ``branch`` frontier cells nearest the
    agent: a far-away ignition cannot hurt it sooner.
    """

    def __init__(
        self, state: State, goal: Cell, costs: CostModel, k: int = 1, branch: int = 6
    ) -> None:
        self.world, self.goal, self.costs, self.k, self.branch = state, goal, costs, k, branch
        self._problems: dict[frozenset[Cell], GridProblem] = {}
        self._remaining: dict[tuple[Cell, frozenset[Cell]], float] = {}

    def root(self, fire_to_move: bool = False) -> FireState:
        return (self.world.agent.pos, self.world.fire, 0.0, fire_to_move)

    def _problem(self, fire: frozenset[Cell]) -> GridProblem:
        if fire not in self._problems:
            world = replace(self.world, fire=fire)
            self._problems[fire] = GridProblem(world, world.agent.pos, {self.goal}, self.costs)
        return self._problems[fire]

    def is_max(self, state: FireState) -> bool:
        return state[3]

    def terminal(self, state: FireState) -> bool:
        return state[0] == self.goal

    def moves(self, state: FireState) -> list[FireMove]:
        agent, fire, _, fire_to_move = state
        rows, cols = self.world.rows, self.world.cols
        if not fire_to_move:
            steps = self._problem(fire).step_cost
            return [(n,) for _, n in moves(agent, rows, cols) if n in steps]
        frontier = {
            n
            for f in fire
            for _, n in moves(f, rows, cols)
            if n not in fire
            and n not in (agent, self.goal)
            and self.world.terrain_at(n) is not Terrain.WALL
        }
        near = sorted(frontier, key=lambda c: (abs(c[0] - agent[0]) + abs(c[1] - agent[1]), c))
        near = near[: self.branch]
        out: list[FireMove] = []
        for size in range(1, self.k + 1):
            out.extend(combinations(near, size))
        return out or [()]  # nothing to ignite: the fire passes

    def result(self, state: FireState, move: FireMove) -> FireState:
        agent, fire, cost, fire_to_move = state
        if fire_to_move:
            return (agent, fire | frozenset(move), cost, False)
        cell = move[0]
        return (cell, fire, cost + self._problem(fire).step_cost[cell], True)

    def evaluate(self, state: FireState) -> float:
        agent, fire, cost, _ = state
        key = (agent, fire)
        if key not in self._remaining:
            if agent in fire:
                self._remaining[key] = math.inf
            else:
                problem = self._problem(fire).retarget(agent, {self.goal})
                h = manhattan(problem.goals, self.costs.min_step)
                found = astar(problem, h, snapshots=0)[0].cost
                self._remaining[key] = math.inf if found is None else found
        return cost + self._remaining[key]


def worst_case_ignition(
    state: State, goal: Cell, costs: CostModel, depth: int = 3, k: int = 1
) -> tuple[tuple[Cell, ...], Trace]:
    """The cells an adversarial fire lights this turn (alpha-beta with the fire to move)."""
    game = FireGame(state, goal, costs, k)
    decision, trace = alphabeta(game, game.root(fire_to_move=True), depth)
    return decision.move or (), trace
