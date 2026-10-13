"""Discrete events that change the world. FIRE_SPREAD is automatic (see fire.py / session.py)."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from .grid import Cell, in_bounds
from .state import State, Status
from .terrain import Terrain


class EventType(StrEnum):
    NEW_FIRE = "NEW_FIRE"
    FIRE_EXTINGUISHED = "FIRE_EXTINGUISHED"
    EXIT_BLOCKED = "EXIT_BLOCKED"
    EXIT_REOPENED = "EXIT_REOPENED"
    OBSTACLE_ADDED = "OBSTACLE_ADDED"
    OBSTACLE_REMOVED = "OBSTACLE_REMOVED"
    FIRE_SPREAD = "FIRE_SPREAD"


# Args: NEW_FIRE/FIRE_EXTINGUISHED/OBSTACLE_REMOVED {pos:[r,c]}; OBSTACLE_ADDED {pos, kind?:
# "WALL"|"RUBBLE"}; EXIT_BLOCKED/EXIT_REOPENED {exit:id}.
POS_EVENTS = {
    EventType.NEW_FIRE,
    EventType.FIRE_EXTINGUISHED,
    EventType.OBSTACLE_ADDED,
    EventType.OBSTACLE_REMOVED,
}
EXIT_EVENTS = {EventType.EXIT_BLOCKED, EventType.EXIT_REOPENED}
OBSTACLE_KINDS = {"WALL": Terrain.WALL, "RUBBLE": Terrain.RUBBLE}


@dataclass(frozen=True)
class Event:
    """Applied when the world is at ``tick`` (i.e. during the transition tick -> tick+1)."""

    tick: int
    type: EventType
    args: dict[str, Any] = field(default_factory=dict)


class EventError(ValueError):
    """The event cannot be applied to this state (reason is human-readable)."""


def parse_pos(value: Any) -> Cell | None:
    if (
        isinstance(value, list | tuple)
        and len(value) == 2
        and all(isinstance(x, int) and not isinstance(x, bool) for x in value)
    ):
        return (value[0], value[1])
    return None


def arg_errors(
    etype: EventType, args: Mapping[str, Any], rows: int, cols: int, exit_ids: Collection[str]
) -> list[str]:
    """Structural problems with an event's args (used by scenario validation)."""
    if etype is EventType.FIRE_SPREAD:
        return ["FIRE_SPREAD is automatic and cannot be scripted"]
    if etype in POS_EVENTS:
        pos = parse_pos(args.get("pos"))
        if pos is None:
            return [f"{etype} needs args.pos as [row, col]"]
        if not in_bounds(pos, rows, cols):
            return [f"{etype} pos {pos} is outside the {rows}x{cols} grid"]
        if etype is EventType.OBSTACLE_ADDED and args.get("kind", "WALL") not in OBSTACLE_KINDS:
            return [f"OBSTACLE_ADDED kind must be one of {sorted(OBSTACLE_KINDS)}"]
        return []
    exit_id = args.get("exit")
    if not isinstance(exit_id, str) or exit_id not in exit_ids:
        return [f"{etype} needs args.exit to be one of {sorted(exit_ids)}"]
    return []


def apply_event(state: State, event: Event) -> State:
    """Apply one event; raises EventError when it conflicts with the current state."""
    errors = arg_errors(event.type, event.args, state.rows, state.cols, [e.id for e in state.exits])
    if errors:
        raise EventError(errors[0])
    match event.type:
        case EventType.NEW_FIRE:
            cell = _pos(event)
            if state.terrain_at(cell) is Terrain.WALL:
                raise EventError(f"cannot ignite {cell}: it is a wall")
            if cell == state.agent.pos:
                raise EventError(f"cannot ignite {cell}: the agent is standing there")
            return replace(state, fire=state.fire | {cell})
        case EventType.FIRE_EXTINGUISHED:
            return replace(state, fire=state.fire - {_pos(event)})
        case EventType.EXIT_BLOCKED | EventType.EXIT_REOPENED:
            ex = state.exit(event.args["exit"])
            return state.with_exit(replace(ex, available=event.type is EventType.EXIT_REOPENED))
        case EventType.OBSTACLE_ADDED:
            return _add_obstacle(state, event)
        case EventType.OBSTACLE_REMOVED:
            cell = _pos(event)
            if state.terrain_at(cell) in (Terrain.WALL, Terrain.RUBBLE):
                return state.with_terrain(cell, Terrain.FLOOR)
            return state
        case _:
            raise EventError(f"{event.type} cannot be applied directly")


def _pos(event: Event) -> Cell:
    pos = parse_pos(event.args.get("pos"))
    assert pos is not None  # checked by arg_errors
    return pos


def _add_obstacle(state: State, event: Event) -> State:
    cell = _pos(event)
    terrain = OBSTACLE_KINDS[event.args.get("kind", "WALL")]
    if state.terrain_at(cell) is Terrain.EXIT:
        raise EventError(f"cannot place an obstacle on the exit at {cell}")
    if terrain is Terrain.WALL:
        occupied = (
            cell == state.agent.pos
            or cell in state.fire
            or any(p.pos == cell and p.status is not Status.EVACUATED for p in state.people)
        )
        if occupied:
            raise EventError(f"cannot wall off {cell}: agent, person or fire is there")
    return state.with_terrain(cell, terrain)
