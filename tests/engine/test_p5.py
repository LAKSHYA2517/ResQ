"""P5: planning graph, HTN decomposition, and the agent-type benchmark."""

import math
from collections.abc import Callable
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from resq.agent.baselines import (
    AGENT_KINDS,
    benchmark,
    goal_policy,
    reflex_policy,
    run_agent,
)
from resq.logic.terms import Atom, atom
from resq.planning.domain import build_domain
from resq.planning.fwd_planner import plan
from resq.planning.htn import TaskNode, decompose
from resq.planning.planning_graph import build_planning_graph
from resq.planning.strips import Action, StripsProblem
from resq.search.router import Router
from resq.trace import GraphLevelBuilt, TaskDecomposed
from resq.world.scenarios import Scenario, initial_state, load_all, random_scenario
from resq.world.state import Status


def grounded(scenario: Scenario, people: list[str] | None = None):  # type: ignore[no-untyped-def]
    state = initial_state(scenario)
    router = Router(state, scenario.params.cost_model)
    ids = people if people is not None else [p.id for p in scenario.people]
    exits = [e for e in state.exits if e.available]
    return state, router, exits, build_domain(state, router, ids, exits)


# --- planning graph ------------------------------------------------------------------------------


def test_planning_graph_levels_and_goal_level(shipped: dict[str, Scenario]) -> None:
    _, _, _, domain = grounded(shipped["basic_rescue"])
    graph, trace = build_planning_graph(domain.problem)
    assert graph.goal == ("Evacuated(p1)",)
    assert graph.goal_level == 4  # travel, pick up, travel, drop off: nothing can be parallel
    assert graph.leveled_off and graph.levels[-1].actions == ()
    s0, s1 = graph.levels[0], graph.levels[1]
    assert set(s0.atoms) == {"At(c0_0)", "HandsFree", "Waiting(p1)", "ExitOpen(e1)"}
    assert s0.atom_mutex == () and "Travel(c0_0, c4_6)" in s0.actions
    assert "keep At(c0_0)" in s0.actions  # persistence (no-op) actions
    # moving away and staying put cannot both happen; being in two places cannot both hold
    assert ("Travel(c0_0, c4_6)", "keep At(c0_0)") in s0.action_mutex
    assert ("At(c0_0)", "At(c4_6)") in s1.atom_mutex
    assert [t.level for t in trace if isinstance(t, GraphLevelBuilt)] == list(
        range(len(graph.levels))
    )


def test_graph_grows_monotonically_and_mutexes_only_disappear(shipped: dict[str, Scenario]) -> None:
    _, _, _, domain = grounded(shipped["multiple_people"])
    graph, _ = build_planning_graph(domain.problem)
    for a, b in zip(graph.levels, graph.levels[1:], strict=False):
        assert set(a.atoms) <= set(b.atoms)
        assert {m for m in b.atom_mutex if set(m) <= set(a.atoms)} <= set(a.atom_mutex)
    assert graph.leveled_off  # the level after the last stored one would be identical
    assert graph.goal_level is not None and graph.goal_level <= 12  # 3 people x 4 actions


def test_unreachable_goal_never_appears(make_scenario: Callable[..., Scenario]) -> None:
    s = make_scenario(exits=[{"id": "e1", "pos": [4, 4], "available": False}])
    state = initial_state(s)
    domain = build_domain(state, Router(state, s.params.cost_model), ["p1"], [])
    graph, _ = build_planning_graph(domain.problem)
    assert graph.goal_level is None and graph.leveled_off
    assert not plan(domain.problem, domain.heuristic)[0].found


def test_goal_already_true_and_level_cap() -> None:
    a, b = atom("A"), atom("B")
    step = Action("Make", ("b",), frozenset({a}), frozenset({b}), frozenset(), 1.0)
    done, _ = build_planning_graph(StripsProblem(frozenset({a}), frozenset({a}), (step,)))
    assert done.goal_level == 0
    capped, _ = build_planning_graph(
        StripsProblem(frozenset({a}), frozenset({b}), (step,)), max_levels=0
    )
    assert capped.goal_level is None and len(capped.levels) == 1 and not capped.leveled_off


def test_each_kind_of_action_mutex_is_detected() -> None:
    def atoms(text: str) -> frozenset[Atom]:
        return frozenset(atom(x) for x in text.split())

    def act(name: str, pre: str, add: str, delete: str) -> Action:
        return Action(name, (), atoms(pre), atoms(add), atoms(delete), 1.0)

    def mutexes(*actions: Action) -> set[tuple[str, str]]:
        graph, _ = build_planning_graph(StripsProblem(atoms("S"), frozenset(), actions))
        return {m for m in graph.levels[0].action_mutex if not any(x.startswith("keep") for x in m)}

    # inconsistent effects only: Y deletes what X adds, and neither needs anything
    assert mutexes(act("X", "", "P", ""), act("Y", "", "Q", "P")) == {("X()", "Y()")}
    # interference only: Y deletes X's precondition
    assert mutexes(act("X", "S", "P", ""), act("Y", "", "Q", "S")) == {("X()", "Y()")}
    # independent actions are not mutex
    assert mutexes(act("X", "S", "P", ""), act("Y", "S", "Q", "")) == set()
    # competing needs: preconditions A and B are themselves mutex one level up
    make_a, make_b = act("MakeA", "S", "A", "S"), act("MakeB", "S", "B", "S")
    graph, _ = build_planning_graph(
        StripsProblem(
            frozenset({atom("S")}),
            frozenset(),
            (make_a, make_b, act("UseA", "A", "P", ""), act("UseB", "B", "Q", "")),
        )
    )
    assert ("A", "B") in graph.levels[1].atom_mutex
    assert ("UseA()", "UseB()") in graph.levels[1].action_mutex


@st.composite
def small_scenarios(draw: st.DrawFn) -> Scenario:
    return random_scenario(draw(st.integers(0, 400)), rows=7, cols=7)


@settings(max_examples=40, deadline=None)
@given(small_scenarios())
def test_prop_goal_level_is_a_lower_bound_on_plan_length(scenario: Scenario) -> None:
    _, _, _, domain = grounded(scenario)
    graph, _ = build_planning_graph(domain.problem)
    best, _ = plan(domain.problem, domain.heuristic)
    if best.found:
        assert graph.goal_level is not None and graph.goal_level <= len(best.steps)
    if graph.goal_level is None and graph.leveled_off:
        assert not best.found  # a goal that never appears non-mutex has no plan


# --- HTN -----------------------------------------------------------------------------------------


def primitives(node: TaskNode) -> list[TaskNode]:
    if node.kind == "primitive":
        return [node]
    return [p for c in node.children for p in primitives(c)]


def test_htn_decomposition_tree_for_one_person(shipped: dict[str, Scenario]) -> None:
    state, router, exits, domain = grounded(shipped["basic_rescue"])
    htn, trace = decompose(state, router, ["p1"], exits)
    best, _ = plan(domain.problem, domain.heuristic)
    assert htn.found and htn.steps == tuple(a.label for a in best.steps)
    assert htn.cost == best.cost == 20
    evacuate = htn.tree.children[0]
    assert evacuate.task == "Evacuate(p1)" and evacuate.kind == "compound"
    assert [c.task for c in evacuate.children] == [
        "Goto(p1)", "PickUp(p1)", "ChooseExit(p1)", "Goto(e1)", "DropOff(p1, e1)",
    ]  # fmt: skip
    assert evacuate.children[2].kind == "choice" and evacuate.children[2].note == "e1: 8"
    assert [p.task for p in primitives(htn.tree)] == list(htn.steps)
    assert htn.tree.cost == sum(p.cost for p in primitives(htn.tree))
    assert isinstance(trace[-1], TaskDecomposed) and trace[-1].task == "EvacuateAll"


def test_htn_plan_is_executable_and_never_beats_the_optimal_planner(
    shipped: dict[str, Scenario],
) -> None:
    for name in ("multiple_people", "showcase", "mass_evacuation"):
        s = shipped[name]
        order = [p.id for p in sorted(s.people, key=lambda p: -p.risk)][:4]
        state, router, exits, domain = grounded(s, order)
        htn, _ = decompose(state, router, order, exits)
        by_label = {a.label: a for a in domain.problem.actions}
        world = domain.problem.initial
        for label in htn.steps:  # every primitive is a real STRIPS action, applicable in turn
            assert by_label[label].applicable(world), (name, label)
            world = by_label[label].apply(world)
        assert domain.problem.goal <= world
        assert math.isclose(htn.cost, sum(by_label[x].cost for x in htn.steps))
        best, _ = plan(domain.problem, domain.heuristic)
        assert htn.cost >= (best.cost or 0) - 1e-9  # fixed methods cannot beat search


def test_htn_methods_for_carrying_being_there_and_failure(
    make_scenario: Callable[..., Scenario],
) -> None:
    s = make_scenario()
    state = initial_state(s)
    router = Router(state, s.params.cost_model)
    held = replace(state, agent=replace(state.agent, carrying="p1")).with_person(
        replace(state.person("p1"), status=Status.CARRIED, pos=state.agent.pos)
    )
    carrying, _ = decompose(held, Router(held, s.params.cost_model), ["p1"], list(state.exits))
    assert carrying.steps == ("Travel(c0_0, c4_4)", "DropOff(p1, e1)")
    assert carrying.tree.children[0].method.startswith("carrying")
    there = replace(state, agent=replace(state.agent, pos=(3, 1)))
    at_person, _ = decompose(there, Router(there, s.params.cost_model), ["p1"], list(state.exits))
    assert at_person.steps[0] == "PickUp(p1)"
    assert at_person.tree.children[0].children[0].method == "already there"
    stuck, _ = decompose(state, router, ["p1"], [])
    assert not stuck.found and "no open exit" in stuck.reason and stuck.steps == ()
    trapped = state.with_person(replace(state.person("p1"), status=Status.TRAPPED))
    assert "no method applies" in decompose(trapped, router, ["p1"], list(state.exits))[0].reason
    gone = state.with_person(replace(state.person("p1"), status=Status.EVACUATED))
    done, _ = decompose(gone, router, ["p1"], list(state.exits))
    assert done.found and done.steps == () and done.cost == 0
    walled = make_scenario(terrain=[".....", ".....", "#####", ".....", "....."])
    ws = initial_state(walled)
    cut, _ = decompose(ws, Router(ws, walled.params.cost_model), ["p1"], list(ws.exits))
    assert not cut.found and "no route" in cut.reason


# --- baseline agents and the benchmark -----------------------------------------------------------


def test_all_three_agents_agree_on_an_open_floor(shipped: dict[str, Scenario]) -> None:
    rows = {k: run_agent(k, shipped["basic_rescue"]) for k in AGENT_KINDS}
    assert all((r.rescued, r.cost, r.ticks, r.finished) == (1, 20, 20, True) for r in rows.values())
    with pytest.raises(ValueError, match="unknown agent kind"):
        run_agent("psychic", shipped["basic_rescue"])


def test_reflex_agent_is_defeated_by_a_wall_that_search_walks_round(
    shipped: dict[str, Scenario],
) -> None:
    s = shipped["dynamic_emergency"]  # a wall with two gaps between the agent and the person
    reflex, goal, utility = (run_agent(k, s) for k in AGENT_KINDS)
    assert reflex.rescued == 0 and reflex.finished  # it gave up pacing at the wall
    assert goal.rescued == utility.rescued == 1


def test_utility_agent_saves_the_critical_person_first(shipped: dict[str, Scenario]) -> None:
    s = shipped["triage_dilemma"]
    goal, utility = run_agent("goal", s), run_agent("utility", s)
    assert utility.rescued == 2 and goal.rescued == 1  # nearest-first loses the one in danger
    assert utility.cost > goal.cost  # and that choice costs path: the trade-off is real


def test_policies_only_propose_legal_steps(shipped: dict[str, Scenario]) -> None:
    for s in shipped.values():
        state = initial_state(s)
        for policy in (reflex_policy, goal_policy):
            action, arg, _ = policy(state, s)
            assert action in ("move", "pick", "drop", "wait")
            if action == "move":
                assert isinstance(arg, tuple) and not state.is_blocked(arg)
                assert abs(arg[0] - state.agent.pos[0]) + abs(arg[1] - state.agent.pos[1]) == 1


def test_benchmark_is_reproducible_and_reports_the_measured_ranking() -> None:
    scenarios = [*load_all().values(), *(random_scenario(i) for i in range(1, 21))]
    rows, summaries = benchmark(scenarios)
    assert benchmark(scenarios) == (rows, summaries)  # seeded: identical on a rerun
    assert len(rows) == 3 * len(scenarios)
    pct = {s.agent: s.rescued_pct for s in summaries}
    # measured, not assumed: if a change to an agent breaks this ordering the test must be
    # updated together with docs/BENCHMARK.md and an explanation
    assert pct["utility"] >= pct["goal"] >= pct["reflex"]
    for s in summaries:
        mine = [r for r in rows if r.agent == s.agent]
        assert s.rescued == sum(r.rescued for r in mine) and s.people == sum(r.people for r in mine)
        assert s.rescued_pct == pytest.approx(100 * s.rescued / s.people)
    assert all(r.rescued <= r.people and r.ticks <= 400 for r in rows)


def test_random_scenarios_are_valid_seeded_and_varied() -> None:
    a, b = random_scenario(7), random_scenario(7)
    assert a == b and a != random_scenario(8)
    assert len(a.people) == 3 and len(a.exits) == 2 and a.params.p_spread == 0.03
    assert random_scenario(3, rows=6, cols=8).terrain[0].__len__() == 8
    initial_state(a)


def test_benchmark_of_nothing_is_empty_not_an_error() -> None:
    rows, summaries = benchmark([])
    assert rows == [] and all(s.rescued_pct == 0 and s.cost_per_rescue is None for s in summaries)
