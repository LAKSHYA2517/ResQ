"""The agent's primitive actions. Each one validates against the world before changing it."""

from dataclasses import replace

from ..world.grid import Cell, moves
from ..world.state import State, Status
from ..world.terrain import CostModel


class ActionError(ValueError):
    """The action is not physically possible in this state."""


def enter_cost(state: State, cell: Cell, costs: CostModel) -> float:
    """Cost of stepping into ``cell`` right now (terrain, plus the Hot-zone surcharge)."""
    base = costs.terrain_cost(state.terrain_at(cell))
    if base is None or cell in state.fire:
        raise ActionError(f"{cell} is impassable")
    return base + (costs.hot_extra if cell in state.hot else 0.0)


def move(state: State, to: Cell) -> State:
    here = state.agent.pos
    if to not in {n for _, n in moves(here, state.rows, state.cols)}:
        raise ActionError(f"{to} is not adjacent to the agent at {here}")
    if state.is_blocked(to):
        raise ActionError(f"{to} is blocked by {'fire' if to in state.fire else 'a wall'}")
    state = replace(state, agent=replace(state.agent, pos=to))
    if state.agent.carrying is not None:  # the carried person moves with the agent
        state = state.with_person(replace(state.person(state.agent.carrying), pos=to))
    return state


def pick_up(state: State, person_id: str) -> State:
    person = next((p for p in state.people if p.id == person_id), None)
    if person is None:
        raise ActionError(f"there is no person {person_id!r}")
    if state.agent.carrying is not None:
        raise ActionError(f"already carrying {state.agent.carrying} (capacity is one)")
    if person.status is not Status.WAITING:
        raise ActionError(f"{person_id} is {person.status.value}, not WAITING")
    if person.pos != state.agent.pos:
        raise ActionError(f"{person_id} is at {person.pos}, the agent is at {state.agent.pos}")
    state = state.with_person(replace(person, status=Status.CARRIED))
    return replace(state, agent=replace(state.agent, carrying=person_id))


def drop_off(state: State, person_id: str, exit_id: str) -> State:
    exit_ = next((e for e in state.exits if e.id == exit_id), None)
    if exit_ is None:
        raise ActionError(f"there is no exit {exit_id!r}")
    if state.agent.carrying != person_id:
        raise ActionError(f"not carrying {person_id}")
    if exit_.pos != state.agent.pos:
        raise ActionError(f"exit {exit_id} is at {exit_.pos}, the agent is at {state.agent.pos}")
    if not exit_.available or exit_.pos in state.fire:
        raise ActionError(f"exit {exit_id} is not usable")
    state = state.with_person(replace(state.person(person_id), status=Status.EVACUATED))
    return replace(state, agent=replace(state.agent, carrying=None))
