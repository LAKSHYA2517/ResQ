"""STRIPS representation: a state is a set of ground atoms, an action has pre/add/delete lists."""

from dataclasses import dataclass, field

from ..logic.terms import Atom

type PlanState = frozenset[Atom]


@dataclass(frozen=True)
class Action:
    name: str
    params: tuple[str, ...]
    pre: frozenset[Atom]
    add: frozenset[Atom]
    delete: frozenset[Atom]
    cost: float

    @property
    def label(self) -> str:
        return f"{self.name}({', '.join(self.params)})"

    def applicable(self, state: PlanState) -> bool:
        return self.pre <= state

    def apply(self, state: PlanState) -> PlanState:
        return (state - self.delete) | self.add


@dataclass(frozen=True)
class StripsProblem:
    initial: PlanState
    goal: frozenset[Atom]
    actions: tuple[Action, ...]  # ground; the order here is the deterministic expansion order


@dataclass(frozen=True)
class Plan:
    found: bool
    steps: tuple[Action, ...]
    cost: float | None  # None when no plan exists
    expanded: int
    generated: int
    max_frontier: int
    reason: str = ""
    time_ms: float = field(default=0.0, compare=False)
