"""Event-sourced world: ``scenario + seed + event log`` fully determines every tick.

Timeline rule: **an event with tick t is part of the state at tick t** (scripted events first,
then logged user events, each in list order). The transition t -> t+1 is: the agent acts
(agent/loop.py), fire spreads, the clock advances, then the events of t+1 are applied.
"""

from dataclasses import replace
from random import Random

from ..trace import EventApplied, EventRejected, FireSpread, Trace
from .events import Event, EventError, apply_event
from .fire import settle, spread
from .scenarios import Scenario, initial_state
from .state import State


def events_at(scenario: Scenario, log: tuple[Event, ...], tick: int) -> tuple[Event, ...]:
    return tuple(e for e in (*scenario.scripted_events, *log) if e.tick == tick)


def apply_events(state: State, events: tuple[Event, ...]) -> tuple[State, Trace]:
    """Apply events in order, then settle person statuses. An event that conflicts with the
    state is rejected with a trace entry instead of crashing the run."""
    trace: Trace = []
    for event in events:
        try:
            state = apply_event(state, event)
            trace.append(EventApplied(state.tick, event.type.value, event.args))
        except EventError as err:
            trace.append(EventRejected(state.tick, event.type.value, event.args, str(err)))
    state, changes = settle(state)
    return state, trace + changes


def spread_tick(scenario: Scenario, state: State) -> tuple[State, Trace]:
    """Fire spreads, then the clock advances. The RNG is derived from ``(seed, tick)``, so any
    tick is reproducible without replaying the whole random stream."""
    tick = state.tick
    state, ignited = spread(state, scenario.params.p_spread, Random(f"{scenario.seed}:{tick}"))
    trace: Trace = [FireSpread(tick, ignited)] if ignited else []
    return replace(state, tick=tick + 1), trace


def start(scenario: Scenario, log: tuple[Event, ...] = ()) -> tuple[State, Trace]:
    """State at tick 0, including any events dated tick 0."""
    return apply_events(initial_state(scenario), events_at(scenario, log, 0))


def advance(scenario: Scenario, state: State, log: tuple[Event, ...] = ()) -> tuple[State, Trace]:
    """World-only tick (no agent): spread, clock, then the next tick's events."""
    state, trace = spread_tick(scenario, state)
    state, more = apply_events(state, events_at(scenario, log, state.tick))
    return state, trace + more


def replay(scenario: Scenario, log: tuple[Event, ...], ticks: int) -> list[tuple[State, Trace]]:
    """World-only states at ticks 0..ticks, each with the trace of how it came about."""
    out = [start(scenario, log)]
    for _ in range(ticks):
        out.append(advance(scenario, out[-1][0], log))
    return out
