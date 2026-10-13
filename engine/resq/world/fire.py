"""Fire dynamics: seeded stochastic spread, and the person status that follows from it."""

from dataclasses import replace
from random import Random

from ..trace import PersonStatusChanged, Trace
from .grid import Cell, moves
from .state import State, Status
from .terrain import Terrain


def spread(state: State, p_spread: float, rng: Random) -> tuple[State, tuple[Cell, ...]]:
    """One spread step. Every (fire cell, eligible neighbour) pair gets one independent draw.

    Eligible = not already fire, not a wall, not the agent's cell. Updates are simultaneous
    (eligibility is judged against the fire set at the start of the step). Cells are visited
    in sorted order so the number and order of RNG draws is deterministic. ``p_spread == 0``
    draws nothing, which reproduces the static-fire behaviour.
    """
    if p_spread <= 0 or not state.fire:
        return state, ()
    ignited: set[Cell] = set()
    for f in sorted(state.fire):
        for _, n in moves(f, state.rows, state.cols):
            if n in state.fire or n == state.agent.pos or state.terrain_at(n) is Terrain.WALL:
                continue
            if rng.random() < p_spread:
                ignited.add(n)
    if not ignited:
        return state, ()
    return replace(state, fire=state.fire | ignited), tuple(sorted(ignited))


def settle(state: State) -> tuple[State, Trace]:
    """A WAITING person standing on fire is TRAPPED; a TRAPPED one off fire is WAITING again.

    "Cut off" trapping (no route) is derived later by the KB from search results, not stored here.
    """
    trace: Trace = []
    for p in state.people:
        new = p.status
        if p.status is Status.WAITING and p.pos in state.fire:
            new = Status.TRAPPED
        elif p.status is Status.TRAPPED and p.pos not in state.fire:
            new = Status.WAITING
        if new is not p.status:
            state = state.with_person(replace(p, status=new))
            trace.append(PersonStatusChanged(p.id, p.status.value, new.value))
    return state, trace
