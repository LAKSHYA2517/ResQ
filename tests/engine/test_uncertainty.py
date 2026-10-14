import math
from collections.abc import Callable
from dataclasses import replace
from itertools import product
from random import Random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from resq.trace import FactorEliminated, InferenceDone
from resq.uncertainty.bayesnet import BayesNet, Node
from resq.uncertainty.exact import elimination, enumeration
from resq.uncertainty.models import (
    assess,
    prior_from_risk,
    read_sensors,
    risk_from_posterior,
    sensor_network,
)
from resq.uncertainty.sampling import SAMPLERS, gibbs, likelihood_weighting, rejection
from resq.world.scenarios import Scenario, initial_state

# AIMA's burglary network: P(Burglary | JohnCalls, MaryCalls) = 0.284 (Russell & Norvig 14.4).
ALARM = BayesNet(
    [
        Node("B", (), {(): 0.001}),
        Node("E", (), {(): 0.002}),
        Node(
            "A",
            ("B", "E"),
            {(True, True): 0.95, (True, False): 0.94, (False, True): 0.29, (False, False): 0.001},
        ),
        Node("J", ("A",), {(True,): 0.90, (False,): 0.05}),
        Node("M", ("A",), {(True,): 0.70, (False,): 0.01}),
    ]
)
CALLS = {"J": True, "M": True}


def test_exact_inference_reproduces_the_textbook_answer() -> None:
    by_enum, trace = enumeration(ALARM, "B", CALLS)
    by_elim, elim_trace = elimination(ALARM, "B", CALLS)
    assert by_enum.p_true == pytest.approx(0.2842, abs=1e-4)
    assert by_elim.p_true == pytest.approx(by_enum.p_true, abs=1e-12)
    assert isinstance(trace[-1], InferenceDone)
    assert [t.variable for t in elim_trace if isinstance(t, FactorEliminated)] == ["A", "E"]
    assert by_enum.work > 0 and by_elim.work > 0


def test_prior_and_evidence_queries() -> None:
    assert enumeration(ALARM, "B", {})[0].p_true == pytest.approx(0.001)
    assert elimination(ALARM, "B", {})[0].p_true == pytest.approx(0.001)
    assert elimination(ALARM, "J", {"A": True})[0].p_true == pytest.approx(0.9)
    for infer in (enumeration, elimination):
        assert infer(ALARM, "J", {"J": True})[0].p_true == 1.0  # query is observed
        assert infer(ALARM, "J", {"J": False})[0].p_true == 0.0
        with pytest.raises(ValueError, match="unknown variable"):
            infer(ALARM, "Nope", {})


def test_impossible_evidence_is_an_error_not_a_number() -> None:
    bn = BayesNet([Node("A", (), {(): 0.0}), Node("B", ("A",), {(True,): 0.5, (False,): 0.0})])
    for infer in (enumeration, elimination):
        with pytest.raises(ValueError, match="probability zero"):
            infer(bn, "A", {"B": True})
    sampled, _ = rejection(bn, "A", {"B": True}, 200, Random(1))
    assert sampled.p_true is None and sampled.used == 0


def test_network_validation() -> None:
    with pytest.raises(ValueError, match="unknown parent"):
        BayesNet([Node("A", ("Z",), {(True,): 0.1, (False,): 0.2})])
    with pytest.raises(ValueError, match="needs exactly 2 rows"):
        BayesNet([Node("A", (), {(): 0.1}), Node("B", ("A",), {(True,): 0.1})])
    with pytest.raises(ValueError, match="not a probability"):
        BayesNet([Node("A", (), {(): 1.5})])
    with pytest.raises(ValueError, match="cycle"):
        BayesNet(
            [
                Node("A", ("B",), {(True,): 0.1, (False,): 0.2}),
                Node("B", ("A",), {(True,): 0.1, (False,): 0.2}),
            ]
        )
    with pytest.raises(ValueError, match="malformed"):
        BayesNet.from_dict({"nodes": [{"name": "A"}]})


def test_network_round_trips_through_json_and_sorts_topologically() -> None:
    shuffled = BayesNet(reversed(list(ALARM.nodes.values())))
    assert shuffled.order.index("A") > shuffled.order.index("B")
    again = BayesNet.from_dict(ALARM.to_dict())
    assert enumeration(again, "B", CALLS)[0].p_true == enumeration(ALARM, "B", CALLS)[0].p_true
    assert ALARM.children("A") == ["J", "M"]


@pytest.mark.parametrize("method", sorted(SAMPLERS))
def test_sampling_converges_to_the_exact_posterior(method: str) -> None:
    bn = sensor_network(0.4)
    evidence = {"Smoke": True, "Heat": False, "Voice": True}
    exact = elimination(bn, "Trapped", evidence)[0].p_true
    result, trace = SAMPLERS[method](bn, "Trapped", evidence, 40_000, Random(7))
    assert result.p_true == pytest.approx(exact, abs=0.02)
    assert result.samples == 40_000 and result.curve[-1] == (40_000, result.p_true)
    assert [n for n, _ in result.curve] == sorted({n for n, _ in result.curve})
    early = abs(next(e for n, e in result.curve if n >= 30) - exact)
    assert abs((result.p_true or 0) - exact) <= early + 0.02  # more samples: no worse
    assert isinstance(trace[-1], InferenceDone)


def test_sampling_is_seeded() -> None:
    bn = sensor_network(0.3)
    e = {"Smoke": True}
    for sampler in (rejection, likelihood_weighting, gibbs):
        a, _ = sampler(bn, "Fire", e, 500, Random(3))
        b, _ = sampler(bn, "Fire", e, 500, Random(3))
        c, _ = sampler(bn, "Fire", e, 500, Random(4))
        assert a == b and a.p_true != c.p_true


def test_rejection_wastes_samples_and_weighting_does_not() -> None:
    bn = sensor_network(0.05)
    e = {"Smoke": True, "Heat": True, "Voice": True}  # unlikely evidence
    rej, _ = rejection(bn, "Fire", e, 5000, Random(1))
    lw, _ = likelihood_weighting(bn, "Fire", e, 5000, Random(1))
    assert rej.used < 0.1 * rej.samples  # most samples contradicted the evidence
    assert lw.used > 0 and lw.p_true is not None
    assert gibbs(bn, "Fire", {"Fire": True}, 50, Random(1))[0].p_true == 1.0


@st.composite
def networks(draw: st.DrawFn) -> tuple[BayesNet, str, dict[str, bool]]:
    n = draw(st.integers(1, 5))
    names = [f"V{i}" for i in range(n)]
    nodes = []
    for i, name in enumerate(names):
        parents = tuple(draw(st.sets(st.sampled_from(names[:i]), max_size=2))) if i else ()
        cpt = {
            row: draw(st.floats(0.05, 0.95)) for row in product((True, False), repeat=len(parents))
        }
        nodes.append(Node(name, tuple(sorted(parents)), cpt))
    query = draw(st.sampled_from(names))
    observed = draw(st.sets(st.sampled_from(names), max_size=3))
    return BayesNet(nodes), query, {v: draw(st.booleans()) for v in sorted(observed)}


@settings(max_examples=200, deadline=None)
@given(networks())
def test_prop_enumeration_and_elimination_agree(
    case: tuple[BayesNet, str, dict[str, bool]],
) -> None:
    bn, query, evidence = case
    a = enumeration(bn, query, evidence)[0].p_true
    b = elimination(bn, query, evidence)[0].p_true
    assert math.isclose(a, b, abs_tol=1e-9)
    assert 0.0 <= a <= 1.0


@settings(max_examples=25, deadline=None)
@given(networks(), st.integers(0, 1000))
def test_prop_likelihood_weighting_tracks_exact(
    case: tuple[BayesNet, str, dict[str, bool]], seed: int
) -> None:
    bn, query, evidence = case
    exact = elimination(bn, query, evidence)[0].p_true
    approx, _ = likelihood_weighting(bn, query, evidence, 20_000, Random(seed))
    assert approx.p_true == pytest.approx(exact, abs=0.05)


# --- the sensor model and Risk(P) ---------------------------------------------------------------


def test_prior_and_risk_mapping() -> None:
    assert [prior_from_risk(r) for r in (0, 2, 5)] == [0.05, 0.4, 0.95]
    assert [risk_from_posterior(p) for p in (0.0, 0.09, 0.1, 0.5, 0.91, 1.0)] == [0, 0, 1, 3, 5, 5]


def test_sensors_read_the_true_world(make_scenario: Callable[..., Scenario]) -> None:
    s = make_scenario(
        fire=[[0, 2]],
        people=[
            {"id": "hot", "pos": [1, 2]},
            {"id": "smoky", "pos": [2, 2]},
            {"id": "clear", "pos": [4, 0]},
        ],
    )
    state = initial_state(s)
    read = {p.id: read_sensors(state, p, seed=1, noise=0.0) for p in state.people}
    assert read["hot"] == {"Smoke": True, "Heat": True, "Voice": True}
    assert read["smoky"] == {"Smoke": True, "Heat": False, "Voice": False}
    assert read["clear"] == {"Smoke": False, "Heat": False, "Voice": False}
    no_fire = replace(state, fire=frozenset())
    assert not any(read_sensors(no_fire, state.people[0], 1, 0.0).values())


def test_more_evidence_means_more_risk(make_scenario: Callable[..., Scenario]) -> None:
    s = make_scenario(
        fire=[[0, 2]],
        people=[
            {"id": "hot", "pos": [1, 2], "risk": 3},
            {"id": "smoky", "pos": [2, 2], "risk": 3},
            {"id": "clear", "pos": [4, 0], "risk": 3},
        ],
    )
    state = initial_state(s)
    hot, smoky, clear = (assess(state, p, seed=1, noise=0.0) for p in state.people)
    assert hot.p_trapped > smoky.p_trapped > clear.p_trapped
    assert hot.risk > smoky.risk >= clear.risk
    assert hot.prior_fire == 0.6 and dict(hot.evidence)["Heat"] is True
    bn = sensor_network(0.6)
    by_enumeration = enumeration(bn, "Trapped", dict(hot.evidence))[0].p_true
    assert hot.p_trapped == pytest.approx(by_enumeration, abs=1e-12)
    # the prior matters too: same clear readings, higher baseline risk
    worried = assess(state, replace(state.people[2], risk=5), 1, 0.0)
    assert worried.p_trapped > clear.p_trapped


def test_sensor_noise_is_seeded_and_really_flips(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario())
    person = state.people[0]
    assert read_sensors(state, person, 5, 0.5) == read_sensors(state, person, 5, 0.5)
    readings = {tuple(read_sensors(state, person, seed, 0.5).values()) for seed in range(40)}
    assert len(readings) > 1
    assert all(read_sensors(state, person, seed, 1.0)["Smoke"] for seed in range(5))  # all flipped


def test_elimination_avoids_the_full_joint_on_a_long_chain() -> None:
    # X0 -> X1 -> ... -> X11: enumeration walks 2^10 hidden assignments per query value,
    # elimination never builds a factor over more than three variables.
    chain = BayesNet(
        [Node("X0", (), {(): 0.3})]
        + [Node(f"X{i}", (f"X{i - 1}",), {(True,): 0.8, (False,): 0.1}) for i in range(1, 12)]
    )
    slow, _ = enumeration(chain, "X11", {"X0": True})
    fast, trace = elimination(chain, "X11", {"X0": True})
    assert fast.p_true == pytest.approx(slow.p_true, abs=1e-12)
    assert slow.work == 2 * 2**10 and fast.work < 200
    assert all(t.rows <= 8 for t in trace if isinstance(t, FactorEliminated))  # 3 variables
