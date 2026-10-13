"""Agent loop: original integration tests 4-9, replay, and run invariants."""

from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from resq.agent.agent import ActionError, drop_off, move, pick_up
from resq.agent.loop import RunStatus, Simulation, Snapshot, act, replay
from resq.logic.terms import atom
from resq.search.router import Router
from resq.trace import ActionExecuted, ActionFailed, EventApplied, PlanAdopted, PlanInvalidated
from resq.world.events import EventError, EventType
from resq.world.grid import moves
from resq.world.scenarios import Scenario, initial_state
from resq.world.state import Status


def statuses(snapshot: Snapshot) -> dict[str, str]:
    return {p.id: p.status.value for p in snapshot.state.people}


def facts(snapshot: Snapshot, pred: str) -> set[str]:
    known = [*snapshot.base_facts, *(d.fact for d in snapshot.derived)]
    return {str(f) for f in known if f.pred == pred}


# --- original test 4: multi-person priority ---------------------------------------------------


def test_4_far_critical_person_beats_near_safe_one(shipped: dict[str, Scenario]) -> None:
    s = shipped["triage_dilemma"]
    head = Simulation(s).head
    near, far = s.people[0], s.people[1]
    assert head.target == far.id == "p2"
    assert [p.person_id for p in head.priorities] == ["p2", "p1"]
    by_id = {p.person_id: p for p in head.priorities}
    router = Router(initial_state(s), s.params.cost_model)  # independent path costs
    for person in (near, far):
        cost = router.route(s.agent, person.pos).cost
        assert by_id[person.id].path_cost == cost
        assert by_id[person.id].score == 5 * person.risk + 3 * person.urgency - (cost or 0)
    assert by_id["p1"].path_cost < by_id["p2"].path_cost  # p1 really is nearer
    assert by_id["p1"].breakdown == "p1: 5×0 + 3×1 − 1×2 = 1"
    assert facts(head, "AtRisk") == {"AtRisk(p2)"} and facts(head, "RescueNow") == {"RescueNow(p2)"}


def test_4b_people_are_rescued_in_priority_order(shipped: dict[str, Scenario]) -> None:
    sim = Simulation(shipped["multiple_people"])
    sim.run()
    order = [s.target for s in sim.history if s.plan_change and s.plan_change.kind != "cheaper"]
    assert order == ["p3", "p2", "p1"]  # risk 5, then 3, then 1
    assert sim.head.status is RunStatus.COMPLETE and sim.head.metrics.rescued == 3


# --- original test 5: blocked exit ------------------------------------------------------------


def test_5_blocked_exit_forces_a_replan_to_the_other_exit(shipped: dict[str, Scenario]) -> None:
    sim = Simulation(shipped["blocked_exit"])
    assert sim.head.memory.steps[-1].action.label == "DropOff(p1, e1)"  # nearest exit first
    while sim.head.tick < 4:
        sim.step()
    at4 = sim.head
    assert at4.replan_reason == "DropOff(p1, e1): precondition ExitOpen(e1) no longer holds"
    assert at4.plan_change is not None and at4.plan_change.kind == "invalid"
    assert "DropOff(p1, e1)" in at4.plan_change.old_steps
    assert at4.memory.steps[-1].action.label == "DropOff(p1, e2)"
    unavailable = next(d for d in at4.derived if d.fact == atom("Unavailable", "e1"))
    assert [str(p) for p in unavailable.premises] == ["Exit(e1, c5_9)", "Blocked(c5_9)"]
    end = sim.run()
    assert end.status is RunStatus.COMPLETE
    assert end.state.person("p1").pos == end.state.exit("e2").pos
    assert end.metrics.replans == 1


# --- original test 6: new fire mid-run ----------------------------------------------------------


def test_6_fire_on_the_route_invalidates_the_plan_and_reroutes(
    shipped: dict[str, Scenario],
) -> None:
    sim = Simulation(shipped["dynamic_emergency"])
    assert (4, 4) in sim.head.route  # the first plan goes through the near gap
    while sim.head.tick < 3:
        sim.step()
    at3 = sim.head
    assert at3.replan_reason == "Travel(c1_1, c7_7): route cell (4, 4) is now on fire"
    assert (4, 4) not in at3.route and (4, 9) in at3.route  # through the other gap now
    kinds = [type(t) for t in at3.trace]
    assert kinds.index(EventApplied) < kinds.index(PlanInvalidated) < kinds.index(PlanAdopted)
    assert "Fire(c4_4)" in facts(at3, "Fire") and "Hot(c3_4)" in facts(at3, "Hot")
    end = sim.run()
    assert end.status is RunStatus.COMPLETE and statuses(end) == {"p1": "EVACUATED"}
    assert all(s.state.agent.pos != (4, 4) for s in sim.history)


# --- original test 7 (agent level): no route --------------------------------------------------


def test_7_impossible_scenario_reports_no_valid_plan(shipped: dict[str, Scenario]) -> None:
    sim = Simulation(shipped["impossible"])
    head = sim.head
    assert head.status is RunStatus.STUCK and head.finished
    assert head.memory.steps == () and head.route == () and head.target is None
    assert head.plan_change is None
    assert len(head.no_plan_reasons) == 1
    assert "A* found no route from the agent at (0, 0) to (5, 5)" in head.no_plan_reasons[0]
    assert facts(head, "Reachable") == set() and facts(head, "Eligible") == set()
    after = sim.step()  # time passes; the agent waits, it never invents a route
    assert after.state.agent.pos == (0, 0)
    assert ActionExecuted(0, "Wait", "no plan to follow", 0.0) in after.trace
    assert sim.run().tick == 1  # already finished: run() does nothing more


# --- original test 8: evacuation status ---------------------------------------------------------


def test_8_evacuation_status_and_measured_cost(shipped: dict[str, Scenario]) -> None:
    sim = Simulation(shipped["basic_rescue"])
    planned = sum(s.action.cost for s in sim.head.memory.steps)
    end = sim.run()
    seen = [statuses(s)["p1"] for s in sim.history]
    assert list(dict.fromkeys(seen)) == ["WAITING", "CARRIED", "EVACUATED"]
    assert end.status is RunStatus.COMPLETE and end.finished
    assert end.state.agent.carrying is None and end.state.agent.pos == (9, 9)
    assert end.state.person("p1").pos == (9, 9)
    assert "Evacuated(p1)" in facts(end, "Evacuated") and facts(end, "Person") == set()
    m = end.metrics
    assert (m.rescued, m.moves, m.plans, m.replans) == (1, 18, 1, 0)
    assert m.path_cost == planned == 20  # static world: what was paid is what was planned
    assert end.tick == 20  # 18 moves + pick-up + drop-off


# --- original test 9: hazard removed -----------------------------------------------------------


def test_9_extinguished_fire_makes_a_person_reachable(
    make_scenario: Callable[..., Scenario],
) -> None:
    s = make_scenario(
        terrain=[".....", "####.", ".....", ".....", "....."],
        fire=[[1, 4]],  # burning in the only gap
        scripted_events=[{"tick": 3, "type": "FIRE_EXTINGUISHED", "args": {"pos": [1, 4]}}],
    )
    sim = Simulation(s)
    assert sim.head.status is RunStatus.STUCK
    assert not sim.head.finished  # a scripted event is still to come
    while sim.head.tick < 3:
        sim.step()
        assert sim.head.state.agent.pos == (0, 0)
    assert sim.history[2].status is RunStatus.STUCK and facts(sim.history[2], "Unsafe")
    at3 = sim.head
    assert facts(at3, "Fire") == set() and facts(at3, "Unsafe") == set()
    assert facts(at3, "Reachable") == {"Reachable(p1)"}
    assert at3.status is RunStatus.RUNNING and at3.plan_change is not None
    assert sim.run().status is RunStatus.COMPLETE


def test_9b_extinguished_fire_opens_a_cheaper_route(
    make_scenario: Callable[..., Scenario],
) -> None:
    s = make_scenario(
        terrain=[".....", ".....", "#.##.", ".....", "....."],
        fire=[[2, 1]],  # the near gap is burning; the far gap at (2, 4) is open
        agent=[0, 1],
        people=[{"id": "p1", "pos": [4, 1]}],
    )
    sim = Simulation(s)
    assert (2, 4) in sim.head.route
    sim.step()
    sim.step()
    before = sim.head
    after = sim.inject(EventType.FIRE_EXTINGUISHED, {"pos": [2, 1]})
    assert after.tick == before.tick  # an event belongs to the tick it happens in
    assert after.plan_change is not None and after.plan_change.kind == "cheaper"
    assert after.replan_reason is not None and "cheaper plan" in after.replan_reason
    assert (2, 1) in after.route and (2, 4) not in after.route
    assert facts(before, "Hot") and facts(after, "Hot") == set()
    assert sim.run().status is RunStatus.COMPLETE


# --- hysteresis ---------------------------------------------------------------------------------

CORRIDOR = {
    "grid_size": [5, 7],
    "terrain": ["#######", "###.###", ".......", "#######", "#######"],
    "agent": [2, 3],
    "people": [
        {"id": "a", "pos": [2, 6], "risk": 3, "urgency": 2},
        {"id": "b", "pos": [2, 0], "risk": 3, "urgency": 2},
    ],
    "exits": [{"id": "e1", "pos": [1, 3]}],
}


def corridor_after_rubble(make_scenario: Callable[..., Scenario], delta: float) -> Simulation:
    sim = Simulation(make_scenario(**CORRIDOR, params={"weights": {"delta": delta}}))
    assert sim.head.target == "a"  # equal scores: lower id wins the tie
    sim.step()
    sim.inject(EventType.OBSTACLE_ADDED, {"pos": [2, 5], "kind": "RUBBLE"})
    assert sim.head.target == "a" and sim.head.plan_change is None  # equal again: no switch
    sim.inject(EventType.OBSTACLE_ADDED, {"pos": [2, 6], "kind": "RUBBLE"})
    return sim


def test_target_switches_only_beyond_the_margin(make_scenario: Callable[..., Scenario]) -> None:
    sim = corridor_after_rubble(make_scenario, delta=1.0)  # b now leads by 2 > 1
    head = sim.head
    assert head.target == "b"
    assert head.plan_change is not None and head.plan_change.kind == "target_switch"
    assert head.replan_reason is not None and "exceeds the margin" in head.replan_reason
    assert head.metrics.replans == 1
    assert sim.run().metrics.rescued == 2


def test_hysteresis_prevents_flip_flopping(make_scenario: Callable[..., Scenario]) -> None:
    sim = corridor_after_rubble(make_scenario, delta=5.0)  # b leads by 2, not by more than 5
    assert sim.head.target == "a" and sim.head.plan_change is None
    assert sim.head.metrics.replans == 0


# --- user events ----------------------------------------------------------------------------------


def test_conflicting_user_event_is_refused_and_not_logged(shipped: dict[str, Scenario]) -> None:
    sim = Simulation(shipped["basic_rescue"])
    before = sim.head
    with pytest.raises(EventError, match="agent is standing there"):
        sim.inject(EventType.NEW_FIRE, {"pos": [0, 0]})
    assert sim.log == [] and sim.head is before


def test_reset_restores_tick_zero(shipped: dict[str, Scenario]) -> None:
    sim = Simulation(shipped["basic_rescue"])
    first = sim.head
    sim.step()
    sim.inject(EventType.NEW_FIRE, {"pos": [9, 0]})
    assert sim.reset() == first and sim.log == [] and len(sim.history) == 1


# --- replay ---------------------------------------------------------------------------------------


def test_replay_reproduces_every_snapshot_of_every_scenario(
    shipped: dict[str, Scenario],
) -> None:
    for s in shipped.values():
        sim = Simulation(s)
        sim.run(120)
        assert replay(s, (), sim.head.tick) == sim.history, s.name


def test_replay_reproduces_a_run_with_user_events(shipped: dict[str, Scenario]) -> None:
    s = shipped["showcase"]
    sim = Simulation(s)
    for _ in range(5):
        sim.step()
    sim.inject(EventType.NEW_FIRE, {"pos": list(sim.head.route[2])})  # fire on the route ahead
    assert sim.head.replan_reason is not None
    for _ in range(3):
        sim.step()
    sim.inject(EventType.EXIT_BLOCKED, {"exit": "e2"})
    sim.run(150)
    rebuilt = replay(s, tuple(sim.log), sim.head.tick)
    assert rebuilt == sim.history
    assert [x.metrics for x in rebuilt] == [x.metrics for x in sim.history]


EVENTS = st.tuples(
    st.integers(0, 20),
    st.sampled_from(list(EventType)),
    st.integers(0, 9),
    st.integers(0, 9),
    st.sampled_from(["e1", "e2", "nope"]),
    st.sampled_from(["WALL", "RUBBLE"]),
)


@settings(max_examples=40, deadline=None)
@given(
    st.sampled_from(["showcase", "spreading_fire", "triage_dilemma", "blocked_exit"]),
    st.integers(0, 10_000),
    st.sampled_from([0.0, 0.05, 0.2]),
    st.lists(EVENTS, max_size=6),
)
def test_prop_replay_reproduces_live_snapshots(
    shipped: dict[str, Scenario],
    name: str,
    seed: int,
    p: float,
    events: list[tuple[int, EventType, int, int, str, str]],
) -> None:
    base = shipped[name]
    s = replace(base, seed=seed, params=replace(base.params, p_spread=p))
    sim = Simulation(s)
    for _ in range(22):
        for tick, etype, r, c, exit_id, kind in events:
            if tick == sim.head.tick:
                with suppress(EventError):  # refused events are not part of the log
                    sim.inject(etype, {"pos": [r, c], "exit": exit_id, "kind": kind})
        sim.step()
    assert replay(s, tuple(sim.log), sim.head.tick) == sim.history
    check_run_invariants(sim)


# --- invariants: nothing shown is ever impossible -----------------------------------------------


def check_run_invariants(sim: Simulation) -> None:
    for prev, cur in zip(sim.history, sim.history[1:], strict=False):
        a, b = prev.state, cur.state
        assert b.tick == a.tick + 1
        assert not b.is_blocked(b.agent.pos)  # the agent is never on a wall or in fire
        neighbours = {n for _, n in moves(a.agent.pos, a.rows, a.cols)}
        assert b.agent.pos == a.agent.pos or b.agent.pos in neighbours
        if len(prev.route) > 1:  # the shown route is the one actually followed
            assert b.agent.pos == prev.route[1]
        assert cur.metrics.path_cost >= prev.metrics.path_cost
    for snap in sim.history:
        state = snap.state
        assert all(not state.is_blocked(c) for c in snap.route[1:])  # routes avoid hazards
        if snap.route:
            assert snap.route[0] == state.agent.pos
        if state.agent.carrying is not None:
            assert state.person(state.agent.carrying).pos == state.agent.pos
            assert state.person(state.agent.carrying).status is Status.CARRIED
        evacuated = sum(p.status is Status.EVACUATED for p in state.people)
        assert snap.metrics.rescued == evacuated
        assert (snap.status is RunStatus.COMPLETE) == (evacuated == len(state.people))
        assert (snap.status is RunStatus.STUCK) == bool(snap.no_plan_reasons)
        known = {*snap.base_facts, *(d.fact for d in snap.derived)}
        assert all(p in known for d in snap.derived for p in d.premises)  # provenance is real


def test_run_invariants_hold_on_every_shipped_scenario(shipped: dict[str, Scenario]) -> None:
    for s in shipped.values():
        sim = Simulation(s)
        sim.run(150)
        check_run_invariants(sim)


def test_showcase_demo_run(shipped: dict[str, Scenario]) -> None:
    """The demo scenario stays interesting: everyone rescued, with real replans on the way."""
    sim = Simulation(shipped["showcase"])
    assert sim.head.target == "p2"  # far and critical beats near and safe
    end = sim.run()
    kinds = {s.plan_change.kind for s in sim.history if s.plan_change}
    assert end.status is RunStatus.COMPLETE and end.metrics.rescued == 3
    assert {"invalid", "cheaper"} <= kinds


# --- primitives ---------------------------------------------------------------------------------


def test_primitive_actions_validate_before_acting(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(
        make_scenario(terrain=[".#...", ".....", ".....", ".....", "....."], fire=[[1, 0]])
    )
    for bad in ((0, 1), (1, 0), (2, 2)):  # wall, fire, not adjacent
        with pytest.raises(ActionError):
            move(state, bad)
    with pytest.raises(ActionError, match="is at"):
        pick_up(state, "p1")
    with pytest.raises(ActionError, match="no person"):
        pick_up(state, "ghost")
    with pytest.raises(ActionError, match="not carrying"):
        drop_off(state, "p1", "e1")
    with pytest.raises(ActionError, match="no exit"):
        drop_off(state, "p1", "ghost")

    there = replace(state, agent=replace(state.agent, pos=(3, 1)))
    carrying = pick_up(there, "p1")
    assert carrying.agent.carrying == "p1" and carrying.person("p1").status is Status.CARRIED
    with pytest.raises(ActionError, match="capacity"):
        pick_up(carrying, "p1")
    with pytest.raises(ActionError, match="not WAITING"):
        pick_up(replace(carrying, agent=replace(carrying.agent, carrying=None)), "p1")
    moved = move(carrying, (3, 2))
    assert moved.person("p1").pos == (3, 2)  # the carried person moves with the agent
    with pytest.raises(ActionError, match="the agent is at"):
        drop_off(moved, "p1", "e1")
    at_exit = replace(moved, agent=replace(moved.agent, pos=(4, 4)))
    blocked = at_exit.with_exit(replace(at_exit.exit("e1"), available=False))
    with pytest.raises(ActionError, match="not usable"):
        drop_off(blocked, "p1", "e1")
    done = drop_off(at_exit, "p1", "e1")
    assert done.agent.carrying is None and done.person("p1").status is Status.EVACUATED


def test_act_refuses_an_illegal_step_instead_of_making_it(shipped: dict[str, Scenario]) -> None:
    s = shipped["basic_rescue"]
    head = Simulation(s).head
    sabotaged = replace(head.state, fire=frozenset({head.route[1]}))  # bypass deliberation
    state, memory, trace = act(s, sabotaged, head.memory)
    assert state is sabotaged and not memory.has_plan
    assert isinstance(trace[0], ActionFailed) and "impassable" in trace[0].reason
