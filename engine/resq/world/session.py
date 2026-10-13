"""Event-sourced simulation: ``scenario + seed + event log`` fully determines every tick."""

from dataclasses import replace
from random import Random

from ..trace import EventApplied, EventRejected, FireSpread, Trace
from .events import Event, EventError, apply_event
from .fire import settle, spread
from .scenarios import Scenario, initial_state
from .state import State


def advance(scenario: Scenario, state: State, log: tuple[Event, ...] = ()) -> tuple[State, Trace]:
    """One tick: events due now, then fire spread, then status settling, then tick += 1.

    Scripted events run before logged (user) events; within each, list order. An event that
    conflicts with the state is rejected with a trace entry rather than crashing the run.
    The RNG is derived from ``(seed, tick)`` so any tick is reproducible without replaying the
    RNG stream (needed by the timeline scrubber).
    """
    tick = state.tick
    trace: Trace = []
    for event in (*scenario.scripted_events, *log):
        if event.tick != tick:
            continue
        try:
            state = apply_event(state, event)
            trace.append(EventApplied(tick, event.type.value, event.args))
        except EventError as err:
            trace.append(EventRejected(tick, event.type.value, event.args, str(err)))
    state, ignited = spread(state, scenario.params.p_spread, Random(f"{scenario.seed}:{tick}"))
    if ignited:
        trace.append(FireSpread(tick, ignited))
    state, changes = settle(state)
    trace.extend(changes)
    return replace(state, tick=tick + 1), trace


def replay(scenario: Scenario, log: tuple[Event, ...], ticks: int) -> list[tuple[State, Trace]]:
    """States at ticks 0..ticks, each with the trace of the transition that produced it."""
    state, _ = settle(initial_state(scenario))
    out: list[tuple[State, Trace]] = [(state, [])]
    for _ in range(ticks):
        state, trace = advance(scenario, state, log)
        out.append((state, trace))
    return out
