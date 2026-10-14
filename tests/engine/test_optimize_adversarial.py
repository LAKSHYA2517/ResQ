"""Local search (rescue order), adversarial search (fire game) and the regression planner."""

import math
from collections.abc import Callable, Sequence
from dataclasses import replace
from itertools import pairwise, permutations
from random import Random

from hypothesis import given, settings
from hypothesis import strategies as st

from resq.decision.ordering import (
    build_order_problem,
    exhaustive,
    greedy_by_priority,
    optimise,
)
from resq.search.adversarial import FireGame, alphabeta, minimax, worst_case_ignition
from resq.search.local import (
    genetic,
    hill_climbing,
    neighbours,
    order_crossover,
    simulated_annealing,
)
from resq.search.router import Router
from resq.trace import GameSearched, OptimizerDone
from resq.world.scenarios import Scenario, initial_state
from resq.world.state import Status

# --- local search --------------------------------------------------------------------------------


def tour_cost(matrix: Sequence[Sequence[float]]) -> Callable[[tuple[int, ...]], float]:
    return lambda order: sum(matrix[a][b] for a, b in pairwise(order))


def test_neighbours_are_distinct_permutations() -> None:
    order = (0, 1, 2, 3)
    ns = list(neighbours(order))
    assert all(sorted(n) == [0, 1, 2, 3] and n != order for n in ns)
    assert len(set(ns)) == len(ns) == 12  # 6 swaps + 6 insertions that are not swaps
    assert list(neighbours((0,))) == []


@settings(max_examples=100, deadline=None)
@given(st.permutations(range(7)), st.permutations(range(7)), st.integers(0, 999))
def test_prop_order_crossover_yields_a_permutation(a: list[int], b: list[int], seed: int) -> None:
    child = order_crossover(tuple(a), tuple(b), Random(seed))
    assert sorted(child) == list(range(7))


MATRICES = st.integers(2, 6).flatmap(
    lambda n: st.lists(st.lists(st.integers(1, 30), min_size=n, max_size=n), min_size=n, max_size=n)
)


@settings(max_examples=40, deadline=None)
@given(MATRICES, st.integers(0, 999))
def test_prop_no_local_search_beats_the_exhaustive_optimum(
    matrix: list[list[float]], seed: int
) -> None:
    n = len(matrix)
    cost = tour_cost(matrix)
    optimum = min(cost(p) for p in permutations(range(n)))
    for run in (
        hill_climbing(n, cost, Random(seed)),
        simulated_annealing(n, cost, Random(seed)),
        genetic(n, cost, Random(seed)),
    ):
        result, trace = run
        assert sorted(result.order) == list(range(n))
        assert result.cost == cost(result.order) >= optimum
        assert list(result.curve) == sorted(result.curve, reverse=True)  # best-so-far only falls
        assert result.curve[-1] == result.cost and result.evaluations > 0
        assert trace == [
            OptimizerDone(result.method, result.order, result.cost, result.evaluations)
        ]


def test_local_search_is_seeded_and_handles_trivial_sizes() -> None:
    matrix = [[(i * 7 + j * 13) % 23 + 1 for j in range(7)] for i in range(7)]
    cost = tour_cost(matrix)
    for algo in (hill_climbing, simulated_annealing, genetic):
        assert algo(7, cost, Random(5))[0] == algo(7, cost, Random(5))[0]
        for n in (0, 1):
            small = algo(n, lambda _o: 0.0, Random(1))[0]
            assert small.order == tuple(range(n)) and small.cost == 0.0


def test_hill_climbing_reaches_a_local_optimum() -> None:
    matrix = [[(i * 5 + j * 11) % 17 + 1 for j in range(6)] for i in range(6)]
    cost = tour_cost(matrix)
    result, _ = hill_climbing(6, cost, Random(2), restarts=1)
    assert all(cost(n) >= result.cost for n in neighbours(result.order))


def test_hill_climbing_stops_as_soon_as_no_neighbour_is_better() -> None:
    # The identity order is already the global optimum: one scan of its neighbours, then stop.
    def misplaced(order: tuple[int, ...]) -> float:
        return float(sum(i != x for i, x in enumerate(order)))

    result, _ = hill_climbing(5, misplaced, Random(1), restarts=1)
    assert result.order == (0, 1, 2, 3, 4) and result.cost == 0
    assert result.evaluations == 1 + len(list(neighbours(result.order)))


# --- rescue-order problem ------------------------------------------------------------------------


def order_problem(scenario: Scenario):  # type: ignore[no-untyped-def]
    state = initial_state(scenario)
    router = Router(state, scenario.params.cost_model)
    weights = {p.id: 5.0 * p.risk + 3.0 * p.urgency for p in scenario.people}
    return state, router, build_order_problem(state, router, weights, list(state.exits))


def test_order_problem_costs_are_real_route_costs(shipped: dict[str, Scenario]) -> None:
    s = shipped["multiple_people"]
    state, router, problem = order_problem(s)
    assert problem.people == ("p1", "p2", "p3") and problem.skipped == ()
    order = (2, 0, 1)  # p3, p1, p2
    # replay the tour leg by leg with independent A* calls
    t, pos, expected = 0.0, state.agent.pos, []
    for i in order:
        person = state.person(problem.people[i])
        exit_ = state.exit(problem.exits[i])
        t += (router.route(pos, person.pos).cost or 0) + 1  # travel + pick-up
        t += (router.route(person.pos, exit_.pos).cost or 0) + 1  # carry + drop-off
        expected.append(t)
        pos = exit_.pos
    assert problem.completion_times(order) == tuple(expected)
    assert problem.cost(order) == sum(
        problem.weights[i] * t for i, t in zip(order, expected, strict=True)
    )
    assert problem.names(order) == ("p3", "p1", "p2")
    for i, pid in enumerate(problem.people):  # the chosen exit really is the nearest one
        person = state.person(pid)
        best = min(router.route(person.pos, e.pos).cost or math.inf for e in state.exits)
        assert problem.carry[i] == best


def test_report_ranks_methods_against_the_computed_optimum(shipped: dict[str, Scenario]) -> None:
    _, _, problem = order_problem(shipped["mass_evacuation"])
    assert len(problem.people) == 7
    report, trace = optimise(problem, seed=3)
    rows = {r.method: r for r in report.rows}
    assert set(rows) == {"greedy", "hill_climbing", "simulated_annealing", "genetic", "exhaustive"}
    assert rows["exhaustive"].cost == report.optimum and rows["exhaustive"].gap == 0
    assert rows["exhaustive"].evaluations == math.factorial(7)
    for r in report.rows:
        assert r.gap is not None and r.gap >= 0  # nothing beats exhaustive search
        assert sorted(r.order) == sorted(problem.people)
        assert r.cost == problem.cost(tuple(problem.people.index(p) for p in r.order))
    gap = {m: r.gap or 0.0 for m, r in rows.items()}
    assert gap["greedy"] > 0  # priority-first really is suboptimal here
    assert min(gap[m] for m in ("hill_climbing", "simulated_annealing", "genetic")) < gap["greedy"]
    assert len(trace) == 3
    assert optimise(problem, seed=3)[0] == report and optimise(problem, seed=4)[0] != report


def test_unreachable_people_are_left_out_with_a_reason(shipped: dict[str, Scenario]) -> None:
    _, _, sealed = order_problem(shipped["impossible"])
    assert sealed.people == () and sealed.skipped == ("p1: no route from the agent",)
    report, _ = optimise(sealed, seed=1)
    assert report.optimum == 0 and all(r.order == () for r in report.rows)
    s = shipped["basic_rescue"]
    state = initial_state(s)
    router = Router(state, s.params.cost_model)
    no_exit = build_order_problem(state, router, {}, [])
    assert no_exit.skipped == ("p1: no reachable open exit",)


def test_exhaustive_is_skipped_beyond_seven_people(shipped: dict[str, Scenario]) -> None:
    _, _, problem = order_problem(shipped["mass_evacuation"])
    eight = replace(
        problem,
        people=(*problem.people, "x"),
        weights=(*problem.weights, 1.0),
        exits=(*problem.exits, problem.exits[0]),
        from_start=(*problem.from_start, 3.0),
        carry=(*problem.carry, 3.0),
        between=(*((*row, 4.0) for row in problem.between), (4.0,) * 8),
    )
    assert exhaustive(eight) is None
    report, _ = optimise(eight, seed=1)
    assert report.optimum is None and all(r.gap is None for r in report.rows)
    assert greedy_by_priority(eight)[0] == max(range(8), key=lambda i: eight.weights[i])


# --- minimax and alpha-beta ----------------------------------------------------------------------


class TreeGame:
    """Explicit game tree: nested lists are choice nodes, numbers are leaves. Root is MAX."""

    def is_max(self, state: tuple[object, int]) -> bool:
        return state[1] % 2 == 0

    def moves(self, state: tuple[object, int]) -> list[int]:
        node = state[0]
        return list(range(len(node))) if isinstance(node, tuple) else []

    def result(self, state: tuple[object, int], move: int) -> tuple[object, int]:
        return (state[0][move], state[1] + 1)  # type: ignore[index]

    def terminal(self, state: tuple[object, int]) -> bool:
        return not isinstance(state[0], tuple)

    def evaluate(self, state: tuple[object, int]) -> float:
        return float(state[0]) if not isinstance(state[0], tuple) else 0.0  # type: ignore[arg-type]


def test_textbook_tree_value_and_pruning() -> None:
    # AIMA figure 5.2: MAX over three MIN nodes; the value is 3 and alpha-beta skips leaves.
    tree = ((3, 12, 8), (2, 4, 6), (14, 5, 2))
    full, trace = minimax(TreeGame(), (tree, 0), 4)
    pruned, _ = alphabeta(TreeGame(), (tree, 0), 4)
    assert (full.value, full.move, full.line) == (3.0, 0, (0, 0))
    assert (pruned.value, pruned.move) == (3.0, 0)
    assert full.nodes == 13 and full.cutoffs == 0
    assert pruned.nodes == 11 and pruned.cutoffs == 2  # the 4 and the 6 are never looked at
    assert trace == [GameSearched("minimax", 4, 3.0, 13, 0)]


TREES = st.recursive(
    st.integers(-20, 20),
    lambda kids: st.lists(kids, min_size=1, max_size=3).map(tuple),
    max_leaves=25,
)


@settings(max_examples=300, deadline=None)
@given(TREES, st.integers(1, 6))
def test_prop_alphabeta_matches_minimax_value_and_move(tree: object, depth: int) -> None:
    full, _ = minimax(TreeGame(), (tree, 0), depth)
    pruned, _ = alphabeta(TreeGame(), (tree, 0), depth)
    assert pruned.value == full.value and pruned.move == full.move
    assert pruned.nodes <= full.nodes


def test_fire_game_same_move_fewer_nodes(shipped: dict[str, Scenario]) -> None:
    s = shipped["showcase"]
    state = initial_state(s)
    goal = state.person("p2").pos
    for depth in (1, 2, 3, 4):
        game = FireGame(state, goal, s.params.cost_model)
        full, _ = minimax(game, game.root(), depth)
        pruned, _ = alphabeta(FireGame(state, goal, s.params.cost_model), game.root(), depth)
        assert pruned.move == full.move and pruned.value == full.value
        assert pruned.nodes <= full.nodes
    assert pruned.nodes < full.nodes and pruned.cutoffs > 0
    assert full.move is not None and full.move[0] in {(3, 4), (5, 4), (4, 3), (4, 5)}
    # depth 1 = the agent just takes the first step of the cheapest route
    calm = Router(state, s.params.cost_model).route(state.agent.pos, goal)
    first = minimax(FireGame(state, goal, s.params.cost_model), game.root(), 1)[0]
    assert first.value == calm.cost and first.move == (calm.path[1],)
    assert full.value >= (calm.cost or 0)  # an adversary can only make it worse


def test_fire_can_cut_the_agent_off(make_scenario: Callable[..., Scenario]) -> None:
    # One-cell-wide corridor with fire beside its middle: one ignition seals it.
    s = make_scenario(
        terrain=["#####", ".....", "##.##", "#####", "#####"],
        agent=[1, 0],
        people=[{"id": "p1", "pos": [1, 4]}],
        exits=[{"id": "e1", "pos": [1, 3]}],
        fire=[[2, 2]],
    )
    state = initial_state(s)
    game = FireGame(state, (1, 4), s.params.cost_model)
    full, trace = minimax(game, game.root(), 2)
    assert math.isinf(full.value)
    assert trace[0] == GameSearched("minimax", 2, None, full.nodes, 0)
    assert alphabeta(game, game.root(), 2)[0].value == full.value
    lit, _ = worst_case_ignition(state, (1, 4), s.params.cost_model, depth=3)
    assert lit == ((1, 2),)  # straight into the corridor
    assert game.evaluate(((1, 2), frozenset({(1, 2)}), 0.0, False)) == math.inf


def test_fire_passes_when_nothing_can_burn(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario())  # no fire at all
    game = FireGame(state, (3, 1), make_scenario().params.cost_model)
    assert game.moves(game.root(fire_to_move=True)) == [()]
    assert worst_case_ignition(state, (3, 1), make_scenario().params.cost_model)[0] == ()
    two = FireGame(
        replace(state, fire=frozenset({(2, 2)})), (3, 1), make_scenario().params.cost_model, k=2
    )
    options = two.moves(two.root(fire_to_move=True))
    assert {len(m) for m in options} == {1, 2} and all(state.agent.pos not in m for m in options)
    assert all(p.status is Status.WAITING for p in state.people)
