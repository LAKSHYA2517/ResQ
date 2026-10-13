"""Typed trace events. Every AI function returns ``(result, trace)``; the UI only renders these."""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TraceEvent:
    @property
    def kind(self) -> str:
        return type(self).__name__

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, **asdict(self)}


type Trace = list[TraceEvent]


# --- search ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeExpanded(TraceEvent):
    state: object
    g: float
    h: float
    f: float
    frontier_size: int


@dataclass(frozen=True)
class PathFound(TraceEvent):
    cost: float
    length: int
    expanded: int


@dataclass(frozen=True)
class SearchFailed(TraceEvent):
    reason: str
    expanded: int


# --- world ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class EventApplied(TraceEvent):
    tick: int
    event_type: str
    args: dict[str, Any]


@dataclass(frozen=True)
class EventRejected(TraceEvent):
    tick: int
    event_type: str
    args: dict[str, Any]
    reason: str


@dataclass(frozen=True)
class FireSpread(TraceEvent):
    tick: int
    ignited: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class PersonStatusChanged(TraceEvent):
    person_id: str
    old: str
    new: str


# --- logic ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleFired(TraceEvent):
    iteration: int
    rule: str
    fact: str
    bindings: tuple[tuple[str, str], ...]
    premises: tuple[str, ...]


@dataclass(frozen=True)
class FixpointReached(TraceEvent):
    iterations: int  # passes run, including the final one that derived nothing
    base_facts: int
    derived_facts: int


# --- agent: routing, decision, planning, acting ------------------------------------------------


@dataclass(frozen=True)
class RouteComputed(TraceEvent):
    src: tuple[int, int]
    dst: tuple[int, int]
    found: bool
    cost: float | None
    expanded: int
    generated: int


@dataclass(frozen=True)
class TargetChosen(TraceEvent):
    target: str | None
    switched: bool
    reason: str


@dataclass(frozen=True)
class PlanStateExpanded(TraceEvent):
    atoms: tuple[str, ...]
    g: float
    h: float
    f: float
    frontier_size: int


@dataclass(frozen=True)
class PlanFound(TraceEvent):
    steps: tuple[str, ...]
    cost: float
    expanded: int


@dataclass(frozen=True)
class PlanFailed(TraceEvent):
    reason: str
    expanded: int


@dataclass(frozen=True)
class PlanInvalidated(TraceEvent):
    reason: str
    steps: tuple[str, ...]
    cursor: int


@dataclass(frozen=True)
class PlanAdopted(TraceEvent):
    change: str  # "initial" | "next_goal" | "invalid" | "target_switch" | "cheaper"
    reason: str
    steps: tuple[str, ...]
    cost: float


@dataclass(frozen=True)
class NoValidPlan(TraceEvent):
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ActionExecuted(TraceEvent):
    tick: int
    action: str  # "Move", "PickUp", "DropOff" or "Wait"
    detail: str
    cost: float


@dataclass(frozen=True)
class ActionFailed(TraceEvent):
    tick: int
    action: str
    reason: str
