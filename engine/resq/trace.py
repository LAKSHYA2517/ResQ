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
