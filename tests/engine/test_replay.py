from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from resq.world.events import Event, EventType
from resq.world.fire import settle
from resq.world.scenarios import Scenario, initial_state
from resq.world.session import advance, replay

LOG = (
    Event(2, EventType.NEW_FIRE, {"pos": [0, 4]}),
    Event(4, EventType.EXIT_BLOCKED, {"exit": "e1"}),
    Event(5, EventType.OBSTACLE_ADDED, {"pos": [3, 0]}),
)


def test_replay_matches_live_run(shipped: dict[str, Scenario]) -> None:
    """Drive the simulation live, injecting events as they arrive; replay must be identical."""
    s = shipped["spreading_fire"]
    state, _ = settle(initial_state(s))
    live = [state]
    log: list[Event] = []
    for tick in range(12):
        if tick in (3, 6):  # a user injects an event at this tick
            log.append(Event(tick, EventType.NEW_FIRE, {"pos": [tick, 9]}))
        state, _ = advance(s, state, tuple(log))
        live.append(state)
    replayed = [st for st, _ in replay(s, tuple(log), 12)]
    assert replayed == live


def test_same_seed_same_run_and_new_seed_differs(shipped: dict[str, Scenario]) -> None:
    s = shipped["spreading_fire"]
    a = [st.fire for st, _ in replay(s, (), 10)]
    b = [st.fire for st, _ in replay(s, (), 10)]
    assert a == b
    other = [st.fire for st, _ in replay(replace(s, seed=s.seed + 1), (), 10)]
    assert other != a
    assert len(a[-1]) > len(a[0])  # p_spread = 0.3 really spreads


def test_replay_trace_has_one_entry_per_tick(shipped: dict[str, Scenario]) -> None:
    out = replay(shipped["dynamic_emergency"], (), 5)
    assert [st.tick for st, _ in out] == [0, 1, 2, 3, 4, 5]
    assert out[0][1] == []
    assert any(t.kind == "EventApplied" for t in out[4][1])  # NEW_FIRE scripted at tick 3


def test_scrubbing_back_is_just_a_prefix(shipped: dict[str, Scenario]) -> None:
    s = shipped["spreading_fire"]
    full = replay(s, LOG, 10)
    assert replay(s, LOG, 4) == full[:5]


@settings(max_examples=60, deadline=None)
@given(
    st.sampled_from(["spreading_fire", "showcase", "triage_dilemma", "multiple_people"]),
    st.integers(0, 10_000),
    st.floats(0.0, 1.0),
    st.lists(
        st.tuples(st.integers(0, 14), st.integers(0, 9), st.integers(0, 9), st.booleans()),
        max_size=6,
    ),
)
def test_prop_replay_reproduces_live_snapshots(
    shipped: dict[str, Scenario],
    name: str,
    seed: int,
    p: float,
    injected: list[tuple[int, int, int, bool]],
) -> None:
    base = shipped[name]
    s = replace(base, seed=seed, params=replace(base.params, p_spread=p))
    log = tuple(
        Event(t, EventType.NEW_FIRE if fire else EventType.FIRE_EXTINGUISHED, {"pos": [r, c]})
        for t, r, c, fire in injected
    )
    state, _ = settle(initial_state(s))
    live = [state]
    for _ in range(15):
        state, _ = advance(s, state, log)
        live.append(state)
    assert [st for st, _ in replay(s, log, 15)] == live
