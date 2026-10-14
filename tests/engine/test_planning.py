import math
from collections.abc import Callable
from dataclasses import replace

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from resq.logic.terms import atom
from resq.planning.domain import HANDS_FREE, PlanStep, RescueDomain, at, build_domain
from resq.planning.fwd_planner import plan
from resq.planning.monitor import remaining_cost, violation
from resq.planning.strips import Action, PlanState, StripsProblem
from resq.search.router import Router
from resq.trace import PlanFailed, PlanFound, PlanStateExpanded
from resq.world.scenarios import Scenario, initial_state, parse_scenario
from resq.world.state import State, Status
from resq.world.terrain import Terrain


def domain_for(scenario: Scenario, people: list[str] | None = None) -> tuple[State, RescueDomain]:
    state = initial_state(scenario)
    router = Router(state, scenario.params.cost_model)
    ids = people if people is not None else [p.id for p in scenario.people]
    return state, build_domain(state, router, ids, [e for e in state.exits if e.available])


def labels(steps: tuple[Action, ...]) -> list[str]:
    return [a.label for a in steps]


def test_action_semantics() -> None:
    a = Action(
        "PickUp",
        ("p1",),
        frozenset({atom("Waiting", "p1"), HANDS_FREE}),
        frozenset({atom("Carrying", "p1")}),
        frozenset({atom("Waiting", "p1"), HANDS_FREE}),
        1.0,
    )
    s = frozenset({atom("Waiting", "p1"), HANDS_FREE, at((0, 0))})
    assert a.label == "PickUp(p1)" and a.applicable(s)
    assert a.apply(s) == {atom("Carrying", "p1"), at((0, 0))}
    assert not a.applicable(a.apply(s))


def test_plan_for_one_person_is_travel_pickup_travel_dropoff(
    shipped: dict[str, Scenario],
) -> None:
    _, domain = domain_for(shipped["basic_rescue"])
    result, trace = plan(domain.problem, domain.heuristic)
    assert labels(result.steps) == [
        "Travel(c0_0, c4_6)",
        "PickUp(p1)",
        "Travel(c4_6, c9_9)",
        "DropOff(p1, e1)",
    ]
    assert result.cost == 10 + 1 + 8 + 1
    assert isinstance(trace[-1], PlanFound) and trace[-1].cost == 20
    assert sum(isinstance(t, PlanStateExpanded) for t in trace) == result.expanded
    steps = domain.steps(result)
    assert steps[0].route[0] == (0, 0) and steps[0].route[-1] == (4, 6)
    assert steps[1].route == ()


def test_planner_chooses_the_cheaper_exit(make_scenario: Callable[..., Scenario]) -> None:
    s = make_scenario(
        people=[{"id": "p1", "pos": [0, 3]}],
        exits=[{"id": "far", "pos": [4, 0]}, {"id": "near", "pos": [0, 4]}],
    )
    _, domain = domain_for(s)
    result, _ = plan(domain.problem, domain.heuristic)
    assert labels(result.steps)[-1] == "DropOff(p1, near)"


def test_no_open_exit_means_no_plan_and_says_why(make_scenario: Callable[..., Scenario]) -> None:
    s = make_scenario(exits=[{"id": "e1", "pos": [4, 4], "available": False}])
    _, domain = domain_for(s)
    result, trace = plan(domain.problem, domain.heuristic)
    assert not result.found and result.cost is None and result.steps == ()
    assert "Evacuated(p1)" in result.reason
    assert isinstance(trace[-1], PlanFailed)
    assert "no exit is open" in domain.notes


def test_unreachable_exit_is_noted(make_scenario: Callable[..., Scenario]) -> None:
    terrain = [".....", ".....", ".....", "...##", "...#."]
    _, domain = domain_for(make_scenario(terrain=terrain))
    assert any("no route" in n and "exit e1" in n for n in domain.notes)
    assert not plan(domain.problem, domain.heuristic)[0].found


def test_replanning_while_carrying_starts_from_the_agent(
    make_scenario: Callable[..., Scenario],
) -> None:
    state = initial_state(make_scenario())
    state = replace(state, agent=replace(state.agent, pos=(3, 1), carrying="p1")).with_person(
        replace(state.person("p1"), status=Status.CARRIED)
    )
    router = Router(state, make_scenario().params.cost_model)
    domain = build_domain(state, router, ["p1"], list(state.exits))
    result, _ = plan(domain.problem, domain.heuristic)
    assert labels(result.steps) == ["Travel(c3_1, c4_4)", "DropOff(p1, e1)"]


def execute(problem: StripsProblem, steps: tuple[Action, ...]) -> PlanState:
    state = problem.initial
    for a in steps:
        assert a.applicable(state), f"{a.label} not applicable"
        state = a.apply(state)
    return state


def test_multi_person_plan_respects_capacity_one(shipped: dict[str, Scenario]) -> None:
    _, domain = domain_for(shipped["multiple_people"])
    result, _ = plan(domain.problem, domain.heuristic)
    assert result.found
    final = execute(domain.problem, result.steps)
    assert domain.problem.goal <= final
    carrying = 0
    for a in result.steps:
        carrying += {"PickUp": 1, "DropOff": -1}.get(a.name, 0)
        assert carrying in (0, 1)
    assert math.isclose(sum(a.cost for a in result.steps), result.cost or 0)


@st.composite
def rescue_scenarios(draw: st.DrawFn) -> Scenario:
    rows, cols = draw(st.integers(5, 7)), draw(st.integers(5, 7))
    chars = draw(
        st.lists(st.sampled_from("...." + "r#"), min_size=rows * cols, max_size=rows * cols)
    )
    terrain = ["".join(chars[r * cols : (r + 1) * cols]) for r in range(rows)]
    free = [(r, c) for r in range(rows) for c in range(cols) if terrain[r][c] != "#"]
    assume(len(free) >= 8)
    picked = draw(st.permutations(free))
    n_people, n_exits = draw(st.integers(1, 3)), draw(st.integers(1, 2))
    raw = {
        "name": "prop",
        "grid_size": [rows, cols],
        "terrain": terrain,
        "agent": list(picked[0]),
        "people": [{"id": f"p{i}", "pos": list(picked[1 + i])} for i in range(n_people)],
        "exits": [{"id": f"e{i}", "pos": list(picked[4 + i])} for i in range(n_exits)],
        "fire": [list(c) for c in picked[6 : 6 + draw(st.integers(0, 2))]],
    }
    scenario, _ = parse_scenario(raw)
    assume(scenario is not None)
    assert scenario is not None
    return scenario


@settings(max_examples=120, deadline=None)
@given(rescue_scenarios())
def test_prop_heuristic_is_admissible_and_plans_are_executable(scenario: Scenario) -> None:
    _, domain = domain_for(scenario)
    informed, _ = plan(domain.problem, domain.heuristic)
    blind, _ = plan(domain.problem)  # uniform-cost: optimal by construction
    assert informed.found == blind.found
    if informed.found:
        assert math.isclose(informed.cost or 0, blind.cost or 0)  # h never overestimates
        assert informed.expanded <= blind.expanded
        assert domain.problem.goal <= execute(domain.problem, informed.steps)
        assert domain.heuristic(domain.problem.initial) <= (informed.cost or 0) + 1e-9


# --- execution monitor --------------------------------------------------------------------------


def planned(
    make_scenario: Callable[..., Scenario], **kw: object
) -> tuple[Scenario, State, tuple[PlanStep, ...]]:
    scenario = make_scenario(**kw)
    state, domain = domain_for(scenario)
    result, _ = plan(domain.problem, domain.heuristic)
    return scenario, state, domain.steps(result)


def test_a_fresh_plan_is_valid_and_costs_what_the_planner_said(
    make_scenario: Callable[..., Scenario],
) -> None:
    scenario, state, steps = planned(make_scenario)
    assert violation(steps, 0, 0, state, list(state.exits)) is None
    router = Router(state, scenario.params.cost_model)
    assert remaining_cost(steps, 0, 0, router) == sum(s.action.cost for s in steps)
    assert remaining_cost(steps, 1, 0, router) == sum(s.action.cost for s in steps[1:])


def test_fire_on_the_route_invalidates_the_plan(make_scenario: Callable[..., Scenario]) -> None:
    _, state, steps = planned(make_scenario)
    cell = steps[0].route[2]
    burning = replace(state, fire=frozenset({cell}))
    reason = violation(steps, 0, 0, burning, list(state.exits))
    assert reason == f"{steps[0].action.label}: route cell {cell} is now on fire"
    # a cell already behind the agent does not matter
    behind = replace(state, agent=replace(state.agent, pos=steps[0].route[3]))
    behind = replace(behind, fire=frozenset({cell}))
    assert violation(steps, 0, 3, behind, list(state.exits)) is None


def test_wall_on_a_later_leg_invalidates_the_plan(make_scenario: Callable[..., Scenario]) -> None:
    _, state, steps = planned(make_scenario)
    cell = steps[2].route[1]
    reason = violation(steps, 0, 0, state.with_terrain(cell, Terrain.WALL), list(state.exits))
    assert reason is not None and "blocked by a wall" in reason and steps[2].action.label in reason


def test_closed_exit_and_lost_person_break_preconditions(
    make_scenario: Callable[..., Scenario],
) -> None:
    _, state, steps = planned(make_scenario)
    assert violation(steps, 0, 0, state, []) == (
        "DropOff(p1, e1): precondition ExitOpen(e1) no longer holds"
    )
    trapped = state.with_person(replace(state.person("p1"), status=Status.TRAPPED))
    assert violation(steps, 0, 0, trapped, list(state.exits)) == (
        "PickUp(p1): precondition Waiting(p1) no longer holds"
    )


def test_agent_off_the_route_is_a_violation(make_scenario: Callable[..., Scenario]) -> None:
    _, state, steps = planned(make_scenario)
    moved = replace(state, agent=replace(state.agent, pos=(0, 4)))
    reason = violation(steps, 0, 0, moved, list(state.exits))
    assert reason is not None and "the agent is at (0, 4)" in reason


def test_remaining_cost_uses_live_step_costs(make_scenario: Callable[..., Scenario]) -> None:
    scenario, state, steps = planned(make_scenario)
    planned_cost = sum(s.action.cost for s in steps)
    # light a fire beside the first leg (not on it): the route is still valid but now Hot
    r, c = steps[0].route[1]
    beside = next(
        n
        for n in [(r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)]
        if state.in_bounds(n) and n not in steps[0].route and n not in steps[2].route
    )
    hot = replace(state, fire=frozenset({beside}))
    assert violation(steps, 0, 0, hot, list(state.exits)) is None
    assert remaining_cost(steps, 0, 0, Router(hot, scenario.params.cost_model)) > planned_cost


# --- regression planner ---------------------------------------------------------------------------

from resq.planning.regression import one_place_one_load, plan_backward  # noqa: E402


def test_regression_finds_the_same_plan_as_forward(shipped: dict[str, Scenario]) -> None:
    _, domain = domain_for(shipped["basic_rescue"])
    forward, _ = plan(domain.problem, domain.heuristic)
    backward, trace = plan_backward(domain.problem, one_place_one_load)
    assert labels(backward.steps) == labels(forward.steps)
    assert backward.cost == forward.cost == 20
    assert isinstance(trace[-1], PlanFound) and trace[-1].steps == tuple(labels(backward.steps))
    assert sum(isinstance(t, PlanStateExpanded) for t in trace) == backward.expanded
    first = next(t for t in trace if isinstance(t, PlanStateExpanded))
    assert first.atoms == ("Evacuated(p1)",)  # regression starts from the goal


def test_regression_reports_an_unreachable_goal(make_scenario: Callable[..., Scenario]) -> None:
    s = make_scenario(exits=[{"id": "e1", "pos": [4, 4], "available": False}])
    _, domain = domain_for(s)
    backward, trace = plan_backward(domain.problem, one_place_one_load)
    assert not backward.found and backward.steps == () and "Evacuated(p1)" in backward.reason
    assert isinstance(trace[-1], PlanFailed)


def test_consistency_pruning_changes_work_not_answers(shipped: dict[str, Scenario]) -> None:
    _, domain = domain_for(shipped["multiple_people"])
    pruned, _ = plan_backward(domain.problem, one_place_one_load)
    plain, _ = plan_backward(domain.problem)
    assert pruned.cost == plain.cost and pruned.expanded < plain.expanded
    assert not one_place_one_load(frozenset({at((0, 0)), at((1, 1))}))
    assert not one_place_one_load(frozenset({atom("Carrying", "a"), HANDS_FREE}))
    assert one_place_one_load(frozenset({at((0, 0)), atom("Carrying", "a")}))


@settings(max_examples=120, deadline=None)
@given(rescue_scenarios())
def test_prop_forward_and_regression_plans_cost_the_same(scenario: Scenario) -> None:
    _, domain = domain_for(scenario)
    forward, _ = plan(domain.problem, domain.heuristic)
    backward, _ = plan_backward(domain.problem, one_place_one_load)
    assert forward.found == backward.found
    if forward.found:
        assert math.isclose(forward.cost or 0, backward.cost or 0)
        assert domain.problem.goal <= execute(domain.problem, backward.steps)
