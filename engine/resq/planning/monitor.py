"""Execution monitoring: is the plan still executable in the live world, and what would it cost?

The world is nondeterministic (fire spreads, exits get blocked), so a plan is only a commitment
until its preconditions stop holding. Checking needs no search: it walks the stored routes and
simulates the remaining actions against the live facts.
"""

from collections.abc import Sequence

from ..search.router import Router
from ..world.state import Exit, State
from .domain import PlanStep, at, live_atoms


def violation(
    steps: Sequence[PlanStep], cursor: int, progress: int, state: State, open_exits: Sequence[Exit]
) -> str | None:
    """The first reason the remaining plan cannot be executed, or ``None`` if it still can.

    ``cursor`` is the current step; ``progress`` is how far along its route the agent is.
    """
    here = state.agent.pos
    atoms = live_atoms(state, open_exits)
    for i in range(cursor, len(steps)):
        action, route = steps[i].action, steps[i].route
        if action.name == "Travel":
            start = progress if i == cursor else 0
            if route[start] != here:
                return f"{action.label}: the agent is at {here}, not at {route[start]}"
            for cell in route[start + 1 :]:
                if state.is_blocked(cell):
                    what = "on fire" if cell in state.fire else "blocked by a wall"
                    return f"{action.label}: route cell {cell} is now {what}"
            here = route[-1]
            continue
        missing = sorted(map(str, action.pre - atoms - {at(here)}))
        if missing:
            return f"{action.label}: precondition {missing[0]} no longer holds"
        atoms = (atoms - action.delete) | action.add
    return None


def remaining_cost(steps: Sequence[PlanStep], cursor: int, progress: int, router: Router) -> float:
    """Cost of finishing a *valid* plan under the live step costs (Hot zones may have moved)."""
    total = 0.0
    for i in range(cursor, len(steps)):
        step = steps[i]
        if step.action.name != "Travel":
            total += step.action.cost
            continue
        for cell in step.route[(progress if i == cursor else 0) + 1 :]:
            total += router.step_cost(cell) or 0.0
    return total
