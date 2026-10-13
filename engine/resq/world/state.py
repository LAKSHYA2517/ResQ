from dataclasses import dataclass, replace
from enum import StrEnum
from functools import cached_property
from typing import Self

from .grid import Cell, in_bounds, moves
from .terrain import Terrain


class Status(StrEnum):
    WAITING = "WAITING"
    CARRIED = "CARRIED"
    EVACUATED = "EVACUATED"
    TRAPPED = "TRAPPED"


@dataclass(frozen=True)
class Person:
    id: str
    pos: Cell
    risk: int = 0  # 0..5, baseline risk (the Bayes net overrides it from P4)
    urgency: int = 0  # 0..5, base urgency
    status: Status = Status.WAITING


@dataclass(frozen=True)
class Exit:
    id: str
    pos: Cell
    available: bool = True


@dataclass(frozen=True)
class Agent:
    pos: Cell
    carrying: str | None = None  # capacity one: a person id or None


@dataclass(frozen=True)
class State:
    """Immutable world snapshot. ``terrain`` has EXIT at exit cells; fire is a separate hazard."""

    rows: int
    cols: int
    terrain: tuple[tuple[Terrain, ...], ...]
    fire: frozenset[Cell]
    agent: Agent
    people: tuple[Person, ...]
    exits: tuple[Exit, ...]
    tick: int = 0

    def in_bounds(self, cell: Cell) -> bool:
        return in_bounds(cell, self.rows, self.cols)

    def terrain_at(self, cell: Cell) -> Terrain:
        return self.terrain[cell[0]][cell[1]]

    def is_fire(self, cell: Cell) -> bool:
        return cell in self.fire

    def is_blocked(self, cell: Cell) -> bool:
        """Impassable: wall or fire."""
        return cell in self.fire or self.terrain_at(cell) is Terrain.WALL

    @cached_property
    def hot(self) -> frozenset[Cell]:
        """Hot zone: passable non-fire cells 4-adjacent to fire. Derived, never stored."""
        out: set[Cell] = set()
        for f in self.fire:
            for _, n in moves(f, self.rows, self.cols):
                if n not in self.fire and self.terrain_at(n) is not Terrain.WALL:
                    out.add(n)
        return frozenset(out)

    def person(self, person_id: str) -> Person:
        return next(p for p in self.people if p.id == person_id)

    def exit(self, exit_id: str) -> Exit:
        return next(e for e in self.exits if e.id == exit_id)

    def with_terrain(self, cell: Cell, terrain: Terrain) -> Self:
        r, c = cell
        row = (*self.terrain[r][:c], terrain, *self.terrain[r][c + 1 :])
        return replace(self, terrain=(*self.terrain[:r], row, *self.terrain[r + 1 :]))

    def with_person(self, person: Person) -> Self:
        return replace(self, people=tuple(person if p.id == person.id else p for p in self.people))

    def with_exit(self, exit_: Exit) -> Self:
        return replace(self, exits=tuple(exit_ if e.id == exit_.id else e for e in self.exits))
