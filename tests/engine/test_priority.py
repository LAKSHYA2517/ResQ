from resq.decision.priority import choose_target, rank, score, urgency
from resq.world.scenarios import Weights

W = Weights()


def test_urgency_grows_with_waiting_and_is_capped() -> None:
    assert urgency(2, 0, W) == 2
    assert urgency(2, 10, W) == 3  # 2 + 0.1 * 10
    assert urgency(4, 1000, W) == W.urgency_cap


def test_score_and_breakdown_match_the_formula() -> None:
    s = score("p2", 4, 3, 10, W)
    assert s.score == 5 * 4 + 3 * 3 - 10 == 19
    assert s.breakdown == "p2: 5×4 + 3×3 − 1×10 = 19"
    assert score("p1", 0, 1.5, 2.5, Weights(w_r=1, w_u=2, w_d=3)).breakdown == (
        "p1: 1×0 + 2×1.5 − 3×2.5 = -4.5"
    )


def test_rank_breaks_ties_by_path_cost_then_id() -> None:
    a = score("a", 2, 2, 4, W)  # 12
    b = score("b", 2, 2, 4, W)  # 12, same cost: id decides
    c = score("c", 3, 0, 3, W)  # 12, lower path cost wins the tie
    d = score("d", 5, 5, 1, W)  # 39
    assert [s.person_id for s in rank([b, a, c, d])] == ["d", "c", "a", "b"]


def test_choose_target_initial_and_empty() -> None:
    ranked = rank([score("a", 1, 1, 1, W), score("b", 3, 3, 1, W)])
    first = choose_target(ranked, None, W.delta)
    assert (first.target, first.switched) == ("b", False)
    none = choose_target((), "a", W.delta)
    assert none.target is None and none.switched
    assert choose_target((), None, W.delta) == choose_target((), None, 0.0)


def test_hysteresis_keeps_the_target_within_the_margin() -> None:
    mine = score("a", 2, 2, 5, W)  # 11
    slightly_better = score("b", 2, 2, 4, W)  # 12: better, but not by more than delta = 2
    choice = choose_target(rank([mine, slightly_better]), "a", W.delta)
    assert (choice.target, choice.switched) == ("a", False)
    assert "within the margin" in choice.reason


def test_hysteresis_switches_beyond_the_margin_and_says_why() -> None:
    mine = score("a", 2, 2, 5, W)  # 11
    much_better = score("b", 3, 2, 4, W)  # 17
    choice = choose_target(rank([mine, much_better]), "a", W.delta)
    assert (choice.target, choice.switched) == ("b", True)
    assert "b (17) vs a (11)" in choice.reason and "δ=2" in choice.reason
    # exactly delta is not enough: the margin must be exceeded
    edge = choose_target(rank([mine, score("b", 2, 2, 3, W)]), "a", W.delta)
    assert edge.target == "a"


def test_target_that_is_no_longer_eligible_is_replaced() -> None:
    choice = choose_target(rank([score("b", 1, 1, 1, W)]), "a", W.delta)
    assert (choice.target, choice.switched) == ("b", True)
    assert "no longer eligible" in choice.reason
    still = choose_target(rank([score("a", 1, 1, 1, W)]), "a", W.delta)
    assert (still.target, still.switched) == ("a", False)
