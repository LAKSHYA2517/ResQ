from collections.abc import Callable
from dataclasses import replace
from random import Random

import pytest

from resq.trace import EventApplied, EventRejected, FireSpread, PersonStatusChanged
from resq.world.events import Event, EventError, EventType, apply_event
from resq.world.fire import settle, spread
from resq.world.scenarios import Scenario, initial_state
from resq.world.session import advance, start
from resq.world.state import Status
from resq.world.terrain import Terrain


def test_no_spread_when_p_is_zero(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario(fire=[[2, 1]]))
    after, ignited = spread(state, 0.0, Random(1))
    assert after is state and ignited == ()


def test_certain_spread_ignites_every_open_neighbour(
    make_scenario: Callable[..., Scenario],
) -> None:
    terrain = [".....", ".#...", ".....", ".....", "....."]
    state = initial_state(make_scenario(terrain=terrain, fire=[[1, 2]]))
    after, ignited = spread(state, 1.0, Random(1))
    assert set(ignited) == {(0, 2), (2, 2), (1, 3)}  # (1,1) is a wall
    assert after.fire == state.fire | set(ignited)


def test_fire_never_spawns_on_agent_or_wall(make_scenario: Callable[..., Scenario]) -> None:
    terrain = [".....", ".....", "..#..", ".....", "....."]
    state = initial_state(make_scenario(terrain=terrain, fire=[[1, 2]], agent=[1, 1]))
    after, _ = spread(state, 1.0, Random(0))
    assert (1, 1) not in after.fire and (2, 2) not in after.fire


def test_spread_is_seeded(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario(fire=[[2, 2]]))
    a = spread(state, 0.5, Random("s:1"))
    b = spread(state, 0.5, Random("s:1"))
    assert a == b
    outcomes = {spread(state, 0.5, Random(f"s:{i}"))[1] for i in range(20)}
    assert len(outcomes) > 1


def test_person_on_fire_is_trapped_and_freed(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario())
    burning = replace(state, fire=frozenset({(3, 1)}))
    trapped, trace = settle(burning)
    assert trapped.person("p1").status is Status.TRAPPED
    assert trace == [PersonStatusChanged("p1", "WAITING", "TRAPPED")]
    freed, _ = settle(replace(trapped, fire=frozenset()))
    assert freed.person("p1").status is Status.WAITING


def test_new_fire_and_extinguish(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario())
    lit = apply_event(state, Event(0, EventType.NEW_FIRE, {"pos": [3, 3]}))
    assert lit.fire == {(3, 3)}
    out = apply_event(lit, Event(1, EventType.FIRE_EXTINGUISHED, {"pos": [3, 3]}))
    assert out.fire == frozenset()


def test_exit_block_and_reopen(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario())
    blocked = apply_event(state, Event(0, EventType.EXIT_BLOCKED, {"exit": "e1"}))
    assert not blocked.exit("e1").available
    assert (
        apply_event(blocked, Event(1, EventType.EXIT_REOPENED, {"exit": "e1"})).exit("e1").available
    )


def test_obstacles(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario())
    walled = apply_event(state, Event(0, EventType.OBSTACLE_ADDED, {"pos": [1, 1]}))
    assert walled.terrain_at((1, 1)) is Terrain.WALL
    rubble = apply_event(
        state, Event(0, EventType.OBSTACLE_ADDED, {"pos": [1, 1], "kind": "RUBBLE"})
    )
    assert rubble.terrain_at((1, 1)) is Terrain.RUBBLE
    cleared = apply_event(walled, Event(1, EventType.OBSTACLE_REMOVED, {"pos": [1, 1]}))
    assert cleared.terrain_at((1, 1)) is Terrain.FLOOR
    assert apply_event(state, Event(0, EventType.OBSTACLE_REMOVED, {"pos": [1, 1]})) == state


@pytest.mark.parametrize(
    "event",
    [
        Event(0, EventType.NEW_FIRE, {"pos": [0, 0]}),  # agent's cell
        Event(0, EventType.NEW_FIRE, {"pos": [9, 9]}),  # off grid
        Event(0, EventType.NEW_FIRE, {}),  # missing pos
        Event(0, EventType.EXIT_BLOCKED, {"exit": "nope"}),
        Event(0, EventType.OBSTACLE_ADDED, {"pos": [3, 1]}),  # wall on a person
        Event(0, EventType.OBSTACLE_ADDED, {"pos": [0, 0]}),  # wall on the agent
        Event(0, EventType.OBSTACLE_ADDED, {"pos": [4, 4], "kind": "RUBBLE"}),  # on an exit
        Event(0, EventType.OBSTACLE_ADDED, {"pos": [1, 1], "kind": "LAVA"}),
        Event(0, EventType.FIRE_SPREAD, {}),
    ],
)
def test_conflicting_events_are_rejected(
    make_scenario: Callable[..., Scenario], event: Event
) -> None:
    state = initial_state(make_scenario())
    with pytest.raises(EventError):
        apply_event(state, event)


def test_wall_cannot_be_ignited(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario(terrain=[".....", ".#...", ".....", ".....", "....."]))
    with pytest.raises(EventError, match="wall"):
        apply_event(state, Event(0, EventType.NEW_FIRE, {"pos": [1, 1]}))


def test_wall_cannot_go_on_fire(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario(fire=[[1, 1]]))
    with pytest.raises(EventError):
        apply_event(state, Event(0, EventType.OBSTACLE_ADDED, {"pos": [1, 1]}))


def test_events_belong_to_their_tick_and_conflicts_are_traced(
    make_scenario: Callable[..., Scenario],
) -> None:
    scenario = make_scenario(
        fire=[[3, 3]],
        params={"p_spread": 1.0},
        scripted_events=[
            {"tick": 0, "type": "EXIT_BLOCKED", "args": {"exit": "e1"}},
            {"tick": 1, "type": "EXIT_REOPENED", "args": {"exit": "e1"}},
        ],
    )
    bad = Event(0, EventType.NEW_FIRE, {"pos": [0, 0]})  # the agent's cell
    state, trace = start(scenario, (bad,))
    assert [type(t) for t in trace] == [EventApplied, EventRejected]
    assert state.tick == 0 and not state.exit("e1").available
    state, trace = advance(scenario, state, (bad,))
    assert [type(t) for t in trace] == [FireSpread, EventApplied]
    assert state.tick == 1 and state.exit("e1").available  # the tick-1 event is in state 1
    assert (3, 2) in state.fire
