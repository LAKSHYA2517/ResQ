"""The agent loop, as pure functions over an event-sourced run.

    OBSERVE -> REPRESENT (state -> base facts) -> REASON (forward chaining)
    -> SELECT GOAL (priority + hysteresis) -> SEARCH (A*) -> PLAN (STRIPS)
    -> ACT (validate, then one primitive action) -> APPLY EVENTS (fire spread, scripted, user)
    -> CHECK PLAN VALIDITY -> RE-PLAN

``deliberate`` is everything up to PLAN (including the validity check of the plan carried over
from the previous tick); ``transition`` is ACT plus fire spread. A run is
``scenario + seed + event log``: ``replay`` rebuilds any tick from those alone.
"""

from dataclasses import dataclass, field, replace
from enum import StrEnum
from time import perf_counter

from ..decision.priority import Choice, PriorityScore, choose_target, rank, score, urgency
from ..logic.forward import forward_chain
from ..logic.kb import KB, Derivation
from ..logic.rules import CORE_RULES, base_facts
from ..logic.terms import Atom, atom
from ..planning.domain import PlanStep, build_domain
from ..planning.fwd_planner import plan as make_plan
from ..planning.monitor import remaining_cost, violation
from ..planning.strips import Plan
from ..search.problem import SearchResult
from ..search.router import Router
from ..trace import (
    ActionExecuted,
    ActionFailed,
    NoValidPlan,
    PlanAdopted,
    PlanInvalidated,
    PlanStateExpanded,
    TargetChosen,
    Trace,
    TraceEvent,
)
from ..world.events import Event, EventType, apply_event
from ..world.grid import Cell
from ..world.scenarios import Scenario, initial_state
from ..world.session import apply_events, spread_tick
from ..world.state import Exit, State, Status
from .agent import ActionError, drop_off, enter_cost, move, pick_up

EPS = 1e-9


class RunStatus(StrEnum):
    RUNNING = "running"  # following a plan
    COMPLETE = "complete"  # everyone evacuated
    STUCK = "stuck"  # no valid plan right now


@dataclass(frozen=True)
class Metrics:
    """Cumulative over the run unless noted. All measured, none estimated."""

    moves: int = 0
    path_cost: float = 0.0  # cost actually paid: cells entered plus pick-ups and drop-offs
    rescued: int = 0
    plans: int = 0  # plans adopted
    replans: int = 0  # unfinished plans that were invalidated or replaced
    searches: int = 0  # A* runs
    nodes_expanded: int = 0  # cells expanded by A*
    plan_nodes_expanded: int = 0  # STRIPS states expanded by the planner
    kb_base: int = 0  # this tick
    kb_derived: int = 0  # this tick
    kb_iterations: int = 0  # this tick
    timings_ms: dict[str, float] = field(default_factory=dict, compare=False)  # this tick


@dataclass(frozen=True)
class Memory:
    """What the agent carries from one tick to the next."""

    target: str | None = None
    steps: tuple[PlanStep, ...] = ()
    cursor: int = 0  # index of the current step
    progress: int = 0  # position along the current Travel route
    layout: tuple[object, ...] | None = None  # world fingerprint the plan was made for
    metrics: Metrics = field(default_factory=Metrics)

    @property
    def has_plan(self) -> bool:
        return self.cursor < len(self.steps)


REPLAN_KINDS = ("invalid", "target_switch", "cheaper")


@dataclass(frozen=True)
class PlanChange:
    kind: str  # "initial" | "next_goal" | "invalid" | "target_switch" | "cheaper"
    reason: str
    old_steps: tuple[str, ...]
    old_cursor: int

    @property
    def is_replan(self) -> bool:
        return self.kind in REPLAN_KINDS


@dataclass(frozen=True)
class Snapshot:
    """Everything observable about one tick. ``trace`` covers how this tick came about: the
    action executed, the world events, then the decisions taken."""

    state: State
    memory: Memory
    status: RunStatus
    finished: bool
    base_facts: tuple[Atom, ...]
    derived: tuple[Derivation, ...]
    priorities: tuple[PriorityScore, ...]
    route: tuple[Cell, ...]  # cells still to walk on the current leg, starting at the agent
    plan_change: PlanChange | None
    no_plan_reasons: tuple[str, ...]
    trace: tuple[TraceEvent, ...]

    @property
    def tick(self) -> int:
        return self.state.tick

    @property
    def target(self) -> str | None:
        return self.memory.target

    @property
    def metrics(self) -> Metrics:
        return self.memory.metrics

    @property
    def replan_reason(self) -> str | None:
        change = self.plan_change
        return change.reason if change is not None and change.is_replan else None


def _layout(state: State) -> tuple[object, ...]:
    return (state.fire, state.terrain, tuple((e.id, e.available) for e in state.exits))


def _why_no_plan(
    state: State,
    kb: KB,
    to_person: dict[str, SearchResult[Cell]],
    notes: list[str],
) -> tuple[str, ...]:
    """The reason chain behind "no valid plan", read off real KB derivations and search results."""
    out: list[str] = []
    for p in state.people:
        if p.status is Status.TRAPPED:
            d = kb.derived.get(atom("Trapped", p.id))
            because = " & ".join(map(str, d.premises)) if d else "they are cut off"
            out.append(f"{p.id} is trapped: {because}")
        elif p.status is Status.WAITING and not to_person[p.id].found:
            r = to_person[p.id]
            out.append(
                f"{p.id}: A* found no route from the agent at {state.agent.pos} to {p.pos}"
                f" ({r.expanded} cells expanded), so Reachable({p.id}) and Eligible({p.id})"
                " do not hold"
            )
    for e in state.exits:
        d = kb.derived.get(atom("Unavailable", e.id))
        if d is not None:
            out.append(f"exit {e.id} is unavailable: {' & '.join(map(str, d.premises))}")
    return tuple(dict.fromkeys([*out, *notes]))


def deliberate(
    scenario: Scenario,
    state: State,
    memory: Memory,
    pre_trace: Trace | None = None,
    earlier_change: PlanChange | None = None,
) -> Snapshot:
    """OBSERVE .. PLAN for one tick, including the validity check of the inherited plan.

    ``earlier_change`` is the plan change already made in this same tick (when a user event
    triggers a second deliberation); it is kept unless this pass changes the plan again.
    """
    w, costs = scenario.params.weights, scenario.params.cost_model
    t0 = perf_counter()
    router = Router(state, costs)

    # SEARCH for reachability and real path costs, then REPRESENT and REASON.
    waiting = [p for p in state.people if p.status is Status.WAITING]
    to_person = {p.id: router.route(state.agent.pos, p.pos) for p in waiting}
    urg = {p.id: urgency(p.urgency, state.tick, w) for p in waiting}
    reachable = {pid for pid, r in to_person.items() if r.found}
    urgent = {pid for pid, u in urg.items() if u >= w.urgent_threshold}
    t1 = perf_counter()
    kb, _ = forward_chain(CORE_RULES, base_facts(state, reachable, urgent))
    t2 = perf_counter()

    # SELECT GOAL. Closed world: an exit is open unless Unavailable(e) was derived.
    ranked = rank(
        score(pid, state.person(pid).risk, urg[pid], to_person[pid].cost or 0.0, w)
        for pid in kb.constants("Eligible")
    )
    open_exits = [e for e in state.exits if not kb.holds(atom("Unavailable", e.id))]
    carrying = state.agent.carrying
    if carrying is not None:
        choice = Choice(carrying, False, f"carrying {carrying}: committed to dropping them off")
        candidates = [carrying]
    else:
        choice = choose_target(ranked, memory.target, w.delta)
        rest = [s.person_id for s in ranked if s.person_id != choice.target]
        candidates = [choice.target, *rest] if choice.target is not None else []

    # CHECK PLAN VALIDITY: decide whether (and why) a new plan is needed.
    layout = _layout(state)
    everyone_out = all(p.status is Status.EVACUATED for p in state.people)
    kind: str | None = None
    reason = ""
    if everyone_out:
        pass  # nothing left to plan for
    elif not memory.has_plan:
        kind = "initial" if memory.metrics.plans == 0 else "next_goal"
        reason = choice.reason
    else:
        broken = violation(memory.steps, memory.cursor, memory.progress, state, open_exits)
        if broken is not None:
            kind, reason = "invalid", broken
        elif choice.target != memory.target:
            kind, reason = "target_switch", choice.reason

    # PLAN (and RE-PLAN).
    trace: Trace = []  # decisions; emitted after the searches and plans they rest on
    planner = _Planner(state, router, open_exits)
    adopted: tuple[str, Plan, tuple[PlanStep, ...]] | None = None
    if kind is not None:
        for pid in candidates:
            found = planner.plan_for(pid)
            if found is not None:
                adopted = (pid, *found)
                break
    elif memory.layout != layout and memory.target is not None:
        # The plan is still executable, but the world changed: adopt a strictly cheaper one.
        found = planner.plan_for(memory.target)
        old_cost = remaining_cost(memory.steps, memory.cursor, memory.progress, router)
        if found is not None and (found[0].cost or 0.0) < old_cost - EPS:
            kind = "cheaper"
            reason = (
                f"cheaper plan after the world changed: remaining cost {old_cost:g} → "
                f"{found[0].cost:g}"
            )
            adopted = (memory.target, *found)
    t3 = perf_counter()

    m = memory.metrics
    change: PlanChange | None = None
    reasons: tuple[str, ...] = ()
    if kind is not None and (adopted is not None or memory.has_plan):
        # Something actually changed: a plan was adopted and/or an unfinished one was dropped.
        old_labels = tuple(s.action.label for s in memory.steps)
        change = PlanChange(kind, reason, old_labels, memory.cursor)
        trace.append(TargetChosen(choice.target, choice.switched, choice.reason))
        if change.is_replan:
            trace.append(PlanInvalidated(reason, old_labels, memory.cursor))
            m = replace(m, replans=m.replans + 1)
        if adopted is not None:
            pid, new_plan, steps = adopted
            labels = tuple(s.action.label for s in steps)
            trace.append(PlanAdopted(kind, reason, labels, new_plan.cost or 0.0))
            memory = replace(memory, target=pid, steps=steps, cursor=0, progress=0)
            m = replace(m, plans=m.plans + 1)
    if kind is not None and adopted is None:
        memory = replace(memory, target=carrying, steps=(), cursor=0, progress=0)
    memory = replace(memory, layout=layout)

    if everyone_out:
        status = RunStatus.COMPLETE
    elif memory.has_plan:
        status = RunStatus.RUNNING
    else:
        status = RunStatus.STUCK
        reasons = _why_no_plan(state, kb, to_person, planner.notes)
        trace.append(NoValidPlan(reasons))
    events_pending = any(e.tick > state.tick for e in scenario.scripted_events)
    finished = everyone_out or (status is RunStatus.STUCK and not events_pending)

    route: tuple[Cell, ...] = ()
    if memory.has_plan and memory.steps[memory.cursor].action.name == "Travel":
        route = memory.steps[memory.cursor].route[memory.progress :]

    m = replace(
        m,
        searches=m.searches + router.searches,
        nodes_expanded=m.nodes_expanded + router.expanded,
        plan_nodes_expanded=m.plan_nodes_expanded + planner.expanded,
        kb_base=len(kb.base),
        kb_derived=len(kb.derived),
        kb_iterations=max((d.iteration for d in kb.derived.values()), default=0) + 1,
        timings_ms={
            "search": router.time_ms,
            "reason": (t2 - t1) * 1000,
            "plan": (t3 - t2) * 1000,
            "total": (perf_counter() - t0) * 1000,
        },
    )
    return Snapshot(
        state=state,
        memory=replace(memory, metrics=m),
        status=status,
        finished=finished,
        base_facts=kb.base,
        derived=tuple(kb.derived.values()),
        priorities=ranked,
        route=route,
        plan_change=change or earlier_change,
        no_plan_reasons=reasons,
        trace=(*(pre_trace or []), *router.trace, *planner.trace, *trace),
    )


class _Planner:
    """Plans single-person evacuations for one deliberation, keeping the bookkeeping together."""

    def __init__(self, state: State, router: Router, open_exits: list[Exit]) -> None:
        self.state, self.router, self.open_exits = state, router, open_exits
        self.notes: list[str] = []
        self.trace: Trace = []
        self.expanded = 0

    def plan_for(self, person_id: str) -> tuple[Plan, tuple[PlanStep, ...]] | None:
        domain = build_domain(self.state, self.router, [person_id], self.open_exits)
        result, trace = make_plan(domain.problem, domain.heuristic)
        self.expanded += result.expanded
        self.trace.extend(e for e in trace if not isinstance(e, PlanStateExpanded))
        if not result.found:
            self.notes.extend(domain.notes)
            self.notes.append(f"{person_id}: {result.reason}")
            return None
        return result, domain.steps(result)


def act(scenario: Scenario, state: State, memory: Memory) -> tuple[State, Memory, Trace]:
    """ACT: validate, then execute exactly one primitive action of the current plan step."""
    tick, m = state.tick, memory.metrics
    if not memory.has_plan:
        return state, memory, [ActionExecuted(tick, "Wait", "no plan to follow", 0.0)]
    step = memory.steps[memory.cursor]
    action = step.action
    try:
        if action.name == "Travel":
            nxt = step.route[memory.progress + 1]
            cost = enter_cost(state, nxt, scenario.params.cost_model)
            new_state = move(state, nxt)
            arrived = memory.progress + 2 == len(step.route)
            memory = replace(
                memory,
                cursor=memory.cursor + arrived,
                progress=0 if arrived else memory.progress + 1,
                metrics=replace(m, moves=m.moves + 1, path_cost=m.path_cost + cost),
            )
            done = ActionExecuted(tick, "Move", f"{state.agent.pos} → {nxt}", cost)
        elif action.name == "PickUp":
            new_state = pick_up(state, action.params[0])
            memory = replace(
                memory,
                cursor=memory.cursor + 1,
                metrics=replace(m, path_cost=m.path_cost + action.cost),
            )
            done = ActionExecuted(tick, "PickUp", action.label, action.cost)
        else:
            new_state = drop_off(state, action.params[0], action.params[1])
            memory = replace(
                memory,
                target=None,
                cursor=memory.cursor + 1,
                metrics=replace(m, rescued=m.rescued + 1, path_cost=m.path_cost + action.cost),
            )
            done = ActionExecuted(tick, "DropOff", action.label, action.cost)
    except ActionError as err:
        # Unreachable while deliberate() validates the plan on this same state; kept so that a
        # bug upstream shows up as a traced failure instead of an illegal move.
        dropped = replace(memory, steps=(), cursor=0, progress=0)
        return state, dropped, [ActionFailed(tick, action.label, str(err))]
    return new_state, memory, [done]


type Entry = tuple[State, Memory, Trace]
"""A tick as it begins: the world after the previous action and fire spread, before this
tick's events are applied and before the agent deliberates."""


def first_entry(scenario: Scenario) -> Entry:
    return initial_state(scenario), Memory(), []


def react(scenario: Scenario, snapshot: Snapshot, event: Event) -> Snapshot:
    """A user event lands on the current tick: apply it, rebuild the facts, re-run inference,
    re-validate the plan the agent had just settled on, and replan if needed."""
    state, trace = apply_events(snapshot.state, (event,))
    pre_trace = [*snapshot.trace, *trace]
    return deliberate(scenario, state, snapshot.memory, pre_trace, snapshot.plan_change)


def enter(scenario: Scenario, entry: Entry, log: tuple[Event, ...]) -> Snapshot:
    """Begin a tick: apply its scripted events and deliberate, then react to each user event
    logged for this tick, in order."""
    state, memory, trace = entry
    tick = state.tick
    scripted = tuple(e for e in scenario.scripted_events if e.tick == tick)
    state, events_trace = apply_events(state, scripted)
    snapshot = deliberate(scenario, state, memory, trace + events_trace)
    for event in log:
        if event.tick == tick:
            snapshot = react(scenario, snapshot, event)
    return snapshot


def transition(scenario: Scenario, snapshot: Snapshot) -> Entry:
    """ACT, then fire spreads and the clock advances."""
    state, memory, trace = act(scenario, snapshot.state, snapshot.memory)
    state, spread_trace = spread_tick(scenario, state)
    return state, memory, trace + spread_trace


def replay(scenario: Scenario, log: tuple[Event, ...], ticks: int) -> list[Snapshot]:
    """Snapshots for ticks 0..ticks rebuilt from nothing but the scenario and the event log."""
    out = [enter(scenario, first_entry(scenario), log)]
    for _ in range(ticks):
        out.append(enter(scenario, transition(scenario, out[-1]), log))
    return out


class Simulation:
    """A live run: the head snapshot, its history, and the user-event log that explains it."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.reset()

    def reset(self) -> Snapshot:
        self.log: list[Event] = []
        self.history = [enter(self.scenario, first_entry(self.scenario), ())]
        return self.head

    @property
    def head(self) -> Snapshot:
        return self.history[-1]

    def step(self) -> Snapshot:
        # Nothing in the log is dated in the future, so the new tick starts with no user events.
        self.history.append(enter(self.scenario, transition(self.scenario, self.head), ()))
        return self.head

    def inject(self, event_type: EventType, args: dict[str, object]) -> Snapshot:
        """Apply a user event to the current tick and re-deliberate. Raises EventError (and
        logs nothing) if the event conflicts with the current state."""
        event = Event(self.head.tick, event_type, dict(args))
        apply_event(self.head.state, event)
        self.log.append(event)
        self.history[-1] = react(self.scenario, self.head, event)
        return self.head

    def run(self, max_ticks: int = 500) -> Snapshot:
        while not self.head.finished and self.head.tick < max_ticks:
            self.step()
        return self.head
