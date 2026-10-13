"""Wire contract (Pydantic v2). The frontend's TypeScript types are generated from these via
OpenAPI, and every value is copied from an engine object: nothing is computed here except
grouping and counting."""

from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel

from resq.agent.loop import Snapshot
from resq.logic.rules import GEOMETRY_PREDICATES
from resq.logic.terms import atom
from resq.world.scenarios import Issue, Scenario

Cell = tuple[int, int]
TerrainName = Literal["floor", "rubble", "wall", "exit"]
StatusName = Literal["WAITING", "CARRIED", "EVACUATED", "TRAPPED"]
EventTypeName = Literal[
    "NEW_FIRE",
    "FIRE_EXTINGUISHED",
    "EXIT_BLOCKED",
    "EXIT_REOPENED",
    "OBSTACLE_ADDED",
    "OBSTACLE_REMOVED",
]

# --- scenarios --------------------------------------------------------------------------------


class PersonModel(BaseModel):
    id: str
    pos: Cell
    risk: int = 0
    urgency: int = 0


class ExitModel(BaseModel):
    id: str
    pos: Cell
    available: bool = True


class ScriptedEventModel(BaseModel):
    tick: int
    type: EventTypeName
    args: dict[str, Any] = {}


class WeightsModel(BaseModel):
    w_r: float
    w_u: float
    w_d: float
    gamma: float
    urgency_cap: float
    urgent_threshold: float
    delta: float


class CostModelModel(BaseModel):
    floor: float
    rubble: float
    exit: float
    hot_extra: float
    pickup: float
    dropoff: float


class ParamsModel(BaseModel):
    p_spread: float
    weights: WeightsModel
    cost_model: CostModelModel


class ScenarioModel(BaseModel):
    """Scenario JSON (brief 6.1). ``terrain`` rows use '.' floor, 'r' rubble, '#' wall."""

    name: str
    grid_size: tuple[int, int]
    terrain: list[str]
    agent: Cell
    people: list[PersonModel]
    fire: list[Cell]
    exits: list[ExitModel]
    scripted_events: list[ScriptedEventModel]
    seed: int
    params: ParamsModel


class ScenarioSummary(BaseModel):
    id: str
    name: str
    predefined: bool
    rows: int
    cols: int
    people: int
    exits: int
    p_spread: float
    scripted_events: int


class ScenarioOut(BaseModel):
    id: str
    predefined: bool
    scenario: ScenarioModel


class IssueOut(BaseModel):
    message: str
    cell: Cell | None
    field: str


class ValidationOut(BaseModel):
    valid: bool
    issues: list[IssueOut]


def validation_out(issues: list[Issue]) -> ValidationOut:
    return ValidationOut(
        valid=not issues,
        issues=[IssueOut(message=i.message, cell=i.cell, field=i.field) for i in issues],
    )


def scenario_summary(sid: str, s: Scenario, predefined: bool) -> ScenarioSummary:
    return ScenarioSummary(
        id=sid,
        name=s.name,
        predefined=predefined,
        rows=s.rows,
        cols=s.cols,
        people=len(s.people),
        exits=len(s.exits),
        p_spread=s.params.p_spread,
        scripted_events=len(s.scripted_events),
    )


def scenario_out(sid: str, s: Scenario, predefined: bool) -> ScenarioOut:
    return ScenarioOut(
        id=sid, predefined=predefined, scenario=ScenarioModel.model_validate(s.to_dict())
    )


# --- snapshots --------------------------------------------------------------------------------


class AgentOut(BaseModel):
    pos: Cell
    carrying: str | None


class PersonOut(BaseModel):
    id: str
    pos: Cell
    risk: int
    urgency: int
    status: StatusName


class ExitOut(BaseModel):
    id: str
    pos: Cell
    available: bool  # the EXIT_BLOCKED flag
    usable: bool  # False when the KB derived Unavailable(exit)


class StateOut(BaseModel):
    tick: int
    rows: int
    cols: int
    terrain: list[list[TerrainName]]
    fire: list[Cell]
    hot: list[Cell]
    agent: AgentOut
    people: list[PersonOut]
    exits: list[ExitOut]


class DerivationOut(BaseModel):
    fact: str
    rule: str
    bindings: dict[str, str]
    premises: list[str]
    iteration: int


class PriorityOut(BaseModel):
    person_id: str
    risk: float
    urgency: float
    path_cost: float
    score: float
    breakdown: str


class PlanStepOut(BaseModel):
    label: str
    name: Literal["Travel", "PickUp", "DropOff"]
    params: list[str]
    cost: float
    status: Literal["done", "current", "pending"]
    route: list[Cell]


class PlanChangeOut(BaseModel):
    kind: Literal["initial", "next_goal", "invalid", "target_switch", "cheaper"]
    reason: str
    is_replan: bool
    old_steps: list[str]
    old_cursor: int


class MetricsOut(BaseModel):
    moves: int
    path_cost: float
    rescued: int
    plans: int
    replans: int
    searches: int
    nodes_expanded: int
    plan_nodes_expanded: int
    kb_base: int
    kb_derived: int
    kb_iterations: int
    timings_ms: dict[str, float]


class TraceEventOut(BaseModel):
    kind: str
    data: dict[str, Any]


class SnapshotOut(BaseModel):
    tick: int
    status: Literal["running", "complete", "stuck"]
    finished: bool
    state: StateOut
    facts: list[str]  # base facts, minus static grid geometry (see fact_counts)
    fact_counts: dict[str, int]  # every predicate, base and derived, including geometry
    derived: list[DerivationOut]
    priorities: list[PriorityOut]
    target: str | None
    plan: list[PlanStepOut]
    route: list[Cell]
    plan_change: PlanChangeOut | None
    replan_reason: str | None
    no_plan_reasons: list[str]
    trace: list[TraceEventOut]
    metrics: MetricsOut


def all_facts(snapshot: Snapshot) -> set[str]:
    return {str(f) for f in snapshot.base_facts} | {str(d.fact) for d in snapshot.derived}


def snapshot_out(snap: Snapshot) -> SnapshotOut:
    state, memory = snap.state, snap.memory
    known = {d.fact for d in snap.derived}
    counts = Counter(f.pred for f in snap.base_facts) + Counter(d.fact.pred for d in snap.derived)
    change = snap.plan_change
    events = [e.to_dict() for e in snap.trace]
    return SnapshotOut(
        tick=snap.tick,
        status=snap.status.value,
        finished=snap.finished,
        state=StateOut(
            tick=state.tick,
            rows=state.rows,
            cols=state.cols,
            terrain=[[t.value for t in row] for row in state.terrain],
            fire=sorted(state.fire),
            hot=sorted(state.hot),
            agent=AgentOut(pos=state.agent.pos, carrying=state.agent.carrying),
            people=[
                PersonOut(id=p.id, pos=p.pos, risk=p.risk, urgency=p.urgency, status=p.status.value)
                for p in state.people
            ],
            exits=[
                ExitOut(
                    id=e.id,
                    pos=e.pos,
                    available=e.available,
                    usable=atom("Unavailable", e.id) not in known,
                )
                for e in state.exits
            ],
        ),
        facts=[str(f) for f in snap.base_facts if f.pred not in GEOMETRY_PREDICATES],
        fact_counts=dict(sorted(counts.items())),
        derived=[
            DerivationOut(
                fact=str(d.fact),
                rule=d.rule,
                bindings=dict(d.bindings),
                premises=[str(p) for p in d.premises],
                iteration=d.iteration,
            )
            for d in snap.derived
        ],
        priorities=[PriorityOut(**vars(p)) for p in snap.priorities],
        target=snap.target,
        plan=[
            PlanStepOut(
                label=s.action.label,
                name=s.action.name,  # type: ignore[arg-type]
                params=list(s.action.params),
                cost=s.action.cost,
                status="done"
                if i < memory.cursor
                else "current"
                if i == memory.cursor
                else "pending",
                route=list(s.route),
            )
            for i, s in enumerate(memory.steps)
        ],
        route=list(snap.route),
        plan_change=None
        if change is None
        else PlanChangeOut(
            kind=change.kind,  # type: ignore[arg-type]
            reason=change.reason,
            is_replan=change.is_replan,
            old_steps=list(change.old_steps),
            old_cursor=change.old_cursor,
        ),
        replan_reason=snap.replan_reason,
        no_plan_reasons=list(snap.no_plan_reasons),
        trace=[TraceEventOut(kind=e.pop("kind"), data=e) for e in events],
        metrics=MetricsOut(**vars(snap.metrics)),
    )


# --- simulation requests / responses -------------------------------------------------------------


class StartIn(BaseModel):
    scenario_id: str
    seed: int | None = None  # overrides the scenario's seed for this session


class SessionIn(BaseModel):
    session_id: str


class EventIn(BaseModel):
    session_id: str
    type: EventTypeName
    args: dict[str, Any] = {}


class SessionOut(BaseModel):
    session_id: str
    scenario_id: str
    seed: int
    snapshot: SnapshotOut


class FactDiff(BaseModel):
    added: list[str]
    removed: list[str]


class EventOut(BaseModel):
    snapshot: SnapshotOut
    diff: FactDiff  # facts (base and derived) before vs after the event
    replan_reason: str | None


class RunOut(BaseModel):
    session_id: str
    running: bool
    speed: float  # ticks per second


class ErrorOut(BaseModel):
    detail: str
