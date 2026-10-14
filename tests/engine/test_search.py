"""Search unit tests, the original integration tests 1, 2, 3, 7, 10, and property tests."""

import math
from collections.abc import Callable
from dataclasses import replace
from itertools import pairwise

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from resq.search import compare, search
from resq.search.heuristics import check_heuristic, make_heuristic, manhattan, weighted
from resq.search.problem import GridProblem
from resq.trace import NodeExpanded, PathFound, SearchFailed
from resq.world.grid import Cell, moves
from resq.world.scenarios import Params, Scenario, initial_state, parse_scenario
from resq.world.state import State
from resq.world.terrain import CostModel, Terrain

ALGOS = ["bfs", "ucs", "astar"]


def route_problem(scenario: Scenario, start: Cell, goal: Cell) -> tuple[State, GridProblem]:
    state = initial_state(scenario)
    return state, GridProblem(state, start, {goal}, scenario.params.cost_model)


def run(problem: GridProblem, algorithm: str, hname: str = "manhattan"):  # type: ignore[no-untyped-def]
    informed = algorithm in ("astar", "greedy", "weighted_astar")
    return search(problem, algorithm, make_heuristic(hname, problem) if informed else None)


def path_cost(problem: GridProblem, path: tuple[Cell, ...]) -> float:
    """Independent recomputation of a path's cost from the problem's step costs."""
    total = 0.0
    for a, b in pairwise(path):
        assert b in {n for _, n in moves(a, problem.rows, problem.cols)}, "non-adjacent step"
        total += problem.step_cost[b]
    return total


# --- original test 1: clear route -------------------------------------------------------


@pytest.mark.parametrize("algorithm", ALGOS)
def test_1_clear_route(shipped: dict[str, Scenario], algorithm: str) -> None:
    s = shipped["basic_rescue"]
    _, problem = route_problem(s, s.agent, s.people[0].pos)
    result, trace = run(problem, algorithm)
    assert result.found and result.path[0] == s.agent and result.path[-1] == s.people[0].pos
    assert result.cost == 10 == len(result.actions)  # open floor: Manhattan distance
    assert path_cost(problem, result.path) == result.cost
    assert isinstance(trace[-1], PathFound)
    assert sum(isinstance(t, NodeExpanded) for t in trace) == result.expanded


# --- original test 2: obstacles ---------------------------------------------------------


@pytest.mark.parametrize("algorithm", ALGOS)
def test_2_obstacles_force_detour(make_scenario: Callable[..., Scenario], algorithm: str) -> None:
    terrain = ["..#..", "..#..", "..#..", "..#..", "....."]
    s = make_scenario(terrain=terrain, people=[{"id": "p1", "pos": [0, 4]}])
    state, problem = route_problem(s, (0, 0), (0, 4))
    result, _ = run(problem, algorithm)
    assert result.cost == 12  # down 4, across 4, up 4 through the single gap
    assert all(state.terrain_at(c) is not Terrain.WALL for c in result.path)


# --- original test 3: fire avoidance ----------------------------------------------------


@pytest.mark.parametrize("algorithm", ALGOS)
def test_3_fire_avoidance(shipped: dict[str, Scenario], algorithm: str) -> None:
    s = shipped["fire_emergency"]
    state, problem = route_problem(s, s.agent, s.people[0].pos)
    result, _ = run(problem, algorithm)
    assert result.found
    assert not set(result.path) & state.fire
    assert path_cost(problem, result.path) == result.cost
    _, nf_problem = route_problem(replace(s, fire=frozenset()), s.agent, s.people[0].pos)
    assert (run(nf_problem, "ucs")[0].cost or 0) < (result.cost or 0)  # fire makes it dearer


# --- original test 7: no route ----------------------------------------------------------


@pytest.mark.parametrize("algorithm", ALGOS)
def test_7_no_route_is_reported_not_faked(shipped: dict[str, Scenario], algorithm: str) -> None:
    s = shipped["impossible"]
    _, problem = route_problem(s, s.agent, s.people[0].pos)
    result, trace = run(problem, algorithm)
    assert not result.found
    assert result.path == () and result.actions == () and result.cost is None
    assert result.reason and result.expanded > 0
    assert isinstance(trace[-1], SearchFailed)


# --- original test 10: search comparison ------------------------------------------------


def test_10_search_comparison_is_computed_honestly(shipped: dict[str, Scenario]) -> None:
    s = shipped["showcase"]
    _, problem = route_problem(s, s.agent, s.people[1].pos)  # far, critical person
    runs = {
        r.label: r
        for r in compare(
            problem,
            [
                ("bfs", None),
                ("ucs", None),
                ("astar", "manhattan"),
                ("astar", "euclidean"),
                ("astar", "zero"),
                ("astar", "weighted"),
            ],
        )
    }
    ucs = runs["ucs"].result
    assert ucs.optimal_vs_ucs is True
    for label in ("astar+manhattan", "astar+euclidean", "astar+zero"):
        assert runs[label].result.optimal_vs_ucs is True
        assert runs[label].result.cost == ucs.cost
    assert runs["astar+manhattan"].result.expanded <= ucs.expanded
    for r in runs.values():  # the flag always agrees with the actual costs
        assert r.result.optimal_vs_ucs == (r.result.cost == ucs.cost)
    assert (runs["bfs"].result.cost or 0) >= (ucs.cost or 0)


def test_hot_zone_makes_ucs_differ_from_bfs(make_scenario: Callable[..., Scenario]) -> None:
    # Fire at (2,2) heats (1,2),(3,2),(2,1),(2,3). The 6-step routes all cross a Hot cell
    # (cost 5 each); the 8-step route over the top row is cheaper.
    s = make_scenario(fire=[[2, 2]], agent=[2, 0], people=[{"id": "p1", "pos": [2, 4]}])
    _, problem = route_problem(s, (2, 0), (2, 4))
    bfs, _ = run(problem, "bfs")
    ucs, _ = run(problem, "ucs")
    assert len(bfs.actions) == 6 and (bfs.cost or 0) >= 10  # fewest steps, but crosses Hot cells
    assert (len(ucs.actions), ucs.cost) == (8, 8)


def test_rubble_makes_ucs_differ_from_bfs(make_scenario: Callable[..., Scenario]) -> None:
    s = make_scenario(
        terrain=[".rrr.", ".....", ".....", ".....", "....."],
        agent=[0, 0],
        people=[{"id": "p1", "pos": [0, 4]}],
    )
    _, problem = route_problem(s, (0, 0), (0, 4))
    bfs, _ = run(problem, "bfs")
    ucs, _ = run(problem, "ucs")
    assert (len(bfs.actions), bfs.cost) == (4, 10)  # straight through 3 rubble cells
    assert (len(ucs.actions), ucs.cost) == (6, 6)  # round the rubble on floor


def test_start_is_goal(make_scenario: Callable[..., Scenario]) -> None:
    _, problem = route_problem(make_scenario(), (0, 0), (0, 0))
    for algorithm in ALGOS:
        result, _ = run(problem, algorithm)
        assert (
            result.found and result.cost == 0 and result.path == ((0, 0),) and result.expanded == 0
        )


def test_unknown_algorithm_and_missing_heuristic(make_scenario: Callable[..., Scenario]) -> None:
    _, problem = route_problem(make_scenario(), (0, 0), (4, 4))
    with pytest.raises(ValueError, match="unknown algorithm"):
        search(problem, "dijkstra")
    with pytest.raises(ValueError, match="needs a heuristic"):
        search(problem, "astar")
    with pytest.raises(ValueError, match="unknown heuristic"):
        make_heuristic("nope", problem)


def test_search_is_deterministic(shipped: dict[str, Scenario]) -> None:
    s = shipped["showcase"]
    _, problem = route_problem(s, s.agent, s.people[1].pos)
    for algorithm in ALGOS:
        a, _ = run(problem, algorithm)
        b, _ = run(problem, algorithm)
        assert replace(a, time_ms=0) == replace(b, time_ms=0)


def test_frontier_snapshots_are_capped(shipped: dict[str, Scenario]) -> None:
    s = shipped["basic_rescue"]
    _, problem = route_problem(s, s.agent, (9, 9))
    for algorithm in ALGOS:
        capped, _ = search(problem, algorithm, make_heuristic("zero", problem), snapshots=8)
        assert 0 < len(capped.frontier_snapshots) <= 8
        off, _ = search(problem, algorithm, make_heuristic("zero", problem), snapshots=0)
        assert off.frontier_snapshots == ()


def test_astar_30x30_is_fast(make_scenario: Callable[..., Scenario]) -> None:
    terrain = [
        "".join("r" if (r * 7 + c * 3) % 5 == 0 else "." for c in range(30)) for r in range(30)
    ]
    s = make_scenario(
        grid_size=[30, 30],
        terrain=terrain,
        agent=[0, 1],
        people=[{"id": "p1", "pos": [29, 28]}],
        exits=[{"id": "e1", "pos": [29, 29]}],
    )
    _, problem = route_problem(s, (0, 1), (29, 28))
    result, _ = run(problem, "astar")
    assert result.found and result.time_ms < 100


# --- heuristics -------------------------------------------------------------------------


def test_manhattan_is_consistent_and_admissible_on_shipped_scenarios(
    shipped: dict[str, Scenario],
) -> None:
    for s in shipped.values():
        _, problem = route_problem(s, s.agent, s.people[0].pos)
        for name in ("manhattan", "euclidean", "zero"):
            check = check_heuristic(problem, make_heuristic(name, problem))
            assert check.admissible and check.consistent, (s.name, name)


def test_weighted_heuristic_is_reported_inadmissible(
    make_scenario: Callable[..., Scenario],
) -> None:
    _, problem = route_problem(make_scenario(), (0, 0), (4, 4))
    h = weighted(manhattan(problem.goals, problem.cost_model.min_step), 5.0)
    check = check_heuristic(problem, h)
    assert not check.admissible and not check.consistent
    assert check.n_admissibility_violations > 0
    _, hv, true = check.admissibility_violations[0]
    assert hv > true


def test_check_reports_capped_but_exact_counts(make_scenario: Callable[..., Scenario]) -> None:
    s = make_scenario(grid_size=[10, 10])
    _, problem = route_problem(s, (0, 0), (9, 9))
    check = check_heuristic(problem, weighted(manhattan(problem.goals, 1.0), 9.0))
    assert len(check.admissibility_violations) == 25
    assert check.n_admissibility_violations > 25


# --- property tests ---------------------------------------------------------------------


@st.composite
def routes(draw: st.DrawFn) -> tuple[Scenario, Cell, Cell]:
    rows, cols = draw(st.integers(5, 9)), draw(st.integers(5, 9))
    chars = draw(
        st.lists(st.sampled_from("..." + "r#"), min_size=rows * cols, max_size=rows * cols)
    )
    terrain = ["".join(chars[r * cols : (r + 1) * cols]) for r in range(rows)]
    free = [(r, c) for r in range(rows) for c in range(cols) if terrain[r][c] != "#"]
    assume(len(free) >= 6)
    picked = draw(st.permutations(free))
    agent, person, exit_ = picked[0], picked[1], picked[2]
    fire = picked[3 : 3 + draw(st.integers(0, 4))]
    cm = CostModel(
        floor=draw(st.sampled_from([1.0, 2.0])),
        rubble=draw(st.sampled_from([1.0, 3.0, 5.0])),
        exit=draw(st.sampled_from([1.0, 2.0])),
        hot_extra=draw(st.sampled_from([0.0, 4.0])),
    )
    raw = {
        "name": "prop",
        "grid_size": [rows, cols],
        "terrain": terrain,
        "agent": list(agent),
        "people": [{"id": "p", "pos": list(person)}],
        "fire": [list(f) for f in fire],
        "exits": [{"id": "e", "pos": list(exit_)}],
    }
    scenario, issues = parse_scenario(raw)
    assume(scenario is not None)
    assert scenario is not None and not issues
    return replace(scenario, params=Params(cost_model=cm)), agent, person


@settings(max_examples=150, deadline=None)
@given(routes())
def test_prop_astar_equals_ucs_and_paths_avoid_hazards(route: tuple[Scenario, Cell, Cell]) -> None:
    scenario, start, goal = route
    state, problem = route_problem(scenario, start, goal)
    ucs, _ = run(problem, "ucs")
    for hname in ("manhattan", "euclidean", "zero"):
        a, _ = run(problem, "astar", hname)
        assert a.found == ucs.found
        assert a.cost == ucs.cost or math.isclose(a.cost or 0, ucs.cost or 0)
        assert check_heuristic(problem, make_heuristic(hname, problem)).consistent
    for r, _ in (run(problem, alg) for alg in ALGOS):
        for cell in r.path[1:]:
            assert not state.is_blocked(cell)
        if r.found:
            assert math.isclose(path_cost(problem, r.path), r.cost or 0)
            assert (r.cost or 0) >= (ucs.cost or 0) - 1e-9  # nothing beats UCS


@settings(max_examples=100, deadline=None)
@given(routes())
def test_prop_bfs_equals_ucs_when_all_costs_equal(route: tuple[Scenario, Cell, Cell]) -> None:
    scenario, start, goal = route
    uniform = replace(scenario, params=Params(cost_model=CostModel(1.0, 1.0, 1.0, 0.0)))
    _, problem = route_problem(uniform, start, goal)
    assert run(problem, "bfs")[0].cost == run(problem, "ucs")[0].cost


# --- P4: DFS, DLS, IDDFS, greedy, weighted A* -----------------------------------------------------

EVERY = ["bfs", "dfs", "dls", "iddfs", "ucs", "greedy", "astar", "weighted_astar"]
COMPLETE = ["bfs", "dfs", "iddfs", "ucs", "greedy", "astar", "weighted_astar"]


def test_all_eight_algorithms_share_one_interface(shipped: dict[str, Scenario]) -> None:
    s = shipped["showcase"]
    _, problem = route_problem(s, s.agent, s.people[1].pos)
    for algorithm in EVERY:
        result, trace = run(problem, algorithm)
        assert result.algorithm == algorithm and result.found
        assert result.path[0] == s.agent and result.path[-1] == s.people[1].pos
        assert path_cost(problem, result.path) == result.cost
        assert sum(isinstance(t, NodeExpanded) for t in trace) == result.expanded
        assert isinstance(trace[-1], PathFound)


def test_dfs_and_greedy_are_honestly_non_optimal(make_scenario: Callable[..., Scenario]) -> None:
    # Open grid, goal straight below the start: DFS dives straight down through the rubble
    # (first legal move in up/down/left/right order); greedy walks straight through it too,
    # because it only looks at h.
    s = make_scenario(
        grid_size=[7, 7],
        terrain=[".......", "...r...", "...r...", "...r...", "...r...", ".......", "......."],
        agent=[0, 3],
        people=[{"id": "p1", "pos": [6, 3]}],
        exits=[{"id": "e1", "pos": [6, 6]}],
    )
    _, problem = route_problem(s, (0, 3), (6, 3))
    rows = {r.label: r.result for r in compare(problem, [(a, None) for a in EVERY], limit=30)}
    best = rows["ucs"].cost
    assert best == 8  # two steps sideways to walk round four rubble cells (4 * 3 = 12 saved)
    assert rows["astar+manhattan"].cost == best and rows["astar+manhattan"].optimal_vs_ucs
    assert (rows["greedy+manhattan"].cost or 0) > (best or 0)
    assert rows["greedy+manhattan"].optimal_vs_ucs is False
    assert rows["greedy+manhattan"].expanded < rows["ucs"].expanded  # but it is fast
    assert (rows["dfs"].cost or 0) > (best or 0) and rows["dfs"].optimal_vs_ucs is False
    assert rows["bfs"].cost == 14 and rows["bfs"].optimal_vs_ucs is False  # fewest steps, dearer


def test_iddfs_finds_fewest_steps_like_bfs_and_repeats_work(shipped: dict[str, Scenario]) -> None:
    s = shipped["showcase"]
    _, problem = route_problem(s, s.agent, s.people[1].pos)
    b, _ = run(problem, "bfs")
    i, _ = run(problem, "iddfs")
    assert len(i.actions) == len(b.actions)
    assert i.depth_limit == len(i.actions)  # stopped at the first limit that reaches the goal
    assert i.expanded > b.expanded  # every shallower pass was redone


def test_dls_reports_cutoff_separately_from_no_route(shipped: dict[str, Scenario]) -> None:
    s = shipped["basic_rescue"]
    _, problem = route_problem(s, s.agent, s.people[0].pos)  # 10 steps away
    short, trace = search(problem, "dls", limit=5)
    assert not short.found and short.reason == "cutoff: no goal within depth limit 5"
    assert short.depth_limit == 5 and isinstance(trace[-1], SearchFailed)
    enough, _ = search(problem, "dls", limit=10)
    assert enough.found and len(enough.actions) <= 10
    blocked = shipped["impossible"]
    _, sealed = route_problem(blocked, blocked.agent, blocked.people[0].pos)
    none, _ = search(sealed, "dls", limit=200)
    assert none.reason == "search space exhausted: no route to any goal"
    deep, _ = search(sealed, "iddfs")
    assert not deep.found and deep.reason.startswith("search space exhausted")
    assert not search(sealed, "dfs")[0].found


def test_weighted_astar_trades_cost_for_speed_within_its_bound(
    make_scenario: Callable[..., Scenario],
) -> None:
    terrain = [
        "".join("r" if (r * 5 + c * 3) % 4 == 0 else "." for c in range(20)) for r in range(20)
    ]
    s = make_scenario(
        grid_size=[20, 20],
        terrain=terrain,
        agent=[0, 1],
        people=[{"id": "p1", "pos": [19, 18]}],
        exits=[{"id": "e1", "pos": [19, 19]}],
    )
    _, problem = route_problem(s, (0, 1), (19, 18))
    h = make_heuristic("manhattan", problem)
    exact, _ = search(problem, "astar", h)
    for w in (1.0, 1.5, 3.0):
        r, _ = search(problem, "weighted_astar", h, w=w)
        assert (exact.cost or 0) <= (r.cost or 0) <= w * (exact.cost or 0) + 1e-9
    fast, _ = search(problem, "weighted_astar", h, w=3.0)
    assert fast.expanded < exact.expanded
    assert search(problem, "weighted_astar", h, w=1.0)[0].cost == exact.cost


def test_informed_algorithms_need_a_heuristic(make_scenario: Callable[..., Scenario]) -> None:
    _, problem = route_problem(make_scenario(), (0, 0), (4, 4))
    for algorithm in ("greedy", "weighted_astar"):
        with pytest.raises(ValueError, match="needs a heuristic"):
            search(problem, algorithm)


def test_compare_labels_and_defaults(make_scenario: Callable[..., Scenario]) -> None:
    _, problem = route_problem(make_scenario(), (0, 0), (4, 4))
    runs = compare(
        problem,
        [("dls", None), ("greedy", None), ("weighted_astar", "euclidean"), ("dfs", "zero")],
        limit=3,
        w=1.5,
    )
    assert [r.label for r in runs] == [
        "dls(limit=3)",
        "greedy+manhattan",
        "weighted_astar(w=1.5)+euclidean",
        "dfs",
    ]
    assert runs[0].result.found is False and runs[0].result.optimal_vs_ucs is False
    assert runs[3].heuristic is None  # uninformed algorithms ignore a heuristic


@settings(max_examples=150, deadline=None)
@given(routes())
def test_prop_every_algorithm_returns_real_paths(route: tuple[Scenario, Cell, Cell]) -> None:
    scenario, start, goal = route
    state, problem = route_problem(scenario, start, goal)
    best, _ = run(problem, "ucs")
    fewest, _ = run(problem, "bfs")
    for algorithm in EVERY:
        r, _ = search(
            problem,
            algorithm,
            make_heuristic("manhattan", problem),
            **({"limit": 100} if algorithm == "dls" else {}),
        )
        assert r.found == best.found, algorithm  # limit 100 exceeds any path in a 9x9 grid
        assert all(not state.is_blocked(c) for c in r.path[1:])
        if r.found:
            assert math.isclose(path_cost(problem, r.path), r.cost or 0), algorithm
            assert (r.cost or 0) >= (best.cost or 0) - 1e-9
            assert len(r.actions) >= len(fewest.actions)
            assert len(set(r.path)) == len(r.path)  # no cell visited twice
    assert len(run(problem, "iddfs")[0].actions) == len(fewest.actions)
