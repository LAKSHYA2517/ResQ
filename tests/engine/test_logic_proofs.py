"""Backward chaining and resolution refutation, checked against forward chaining."""

from collections.abc import Callable

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from resq.logic.backward import ProofNode, prove
from resq.logic.forward import forward_chain
from resq.logic.resolution import Literal, refute, resolve, rule_clause, show
from resq.logic.rules import CORE_RULES, base_facts
from resq.logic.terms import Atom, atom, parse_atom, parse_rule, parse_rules
from resq.trace import BackwardStep, Resolved
from resq.world.scenarios import Scenario, initial_state

FAMILY = parse_rules(
    """
    parent_anc:  Parent(X, Y) -> Ancestor(X, Y)
    trans_anc:   Parent(X, Y) & Ancestor(Y, Z) -> Ancestor(X, Z)
    """
)
PARENTS = [atom("Parent", "ann", "bob"), atom("Parent", "bob", "cat"), atom("Parent", "cat", "dan")]


def leaves(node: ProofNode) -> list[Atom]:
    return [node.goal] if node.rule is None else [x for c in node.children for x in leaves(c)]


def rules_used(node: ProofNode) -> set[str]:
    own = {node.rule} if node.rule else set()
    return own.union(*(rules_used(c) for c in node.children))


# --- backward chaining ---------------------------------------------------------------------------


def test_ground_goal_has_a_proof_tree_down_to_base_facts() -> None:
    proofs, trace = prove(FAMILY, PARENTS, atom("Ancestor", "ann", "dan"))
    assert len(proofs) == 1 and proofs[0].bindings == ()
    tree = proofs[0].tree
    assert tree.goal == atom("Ancestor", "ann", "dan") and tree.rule == "trans_anc"
    assert [str(c.goal) for c in tree.children] == ["Parent(ann, bob)", "Ancestor(bob, dan)"]
    assert leaves(tree) == PARENTS  # the proof bottoms out in exactly the three base facts
    assert all(isinstance(t, BackwardStep) for t in trace) and trace


def test_query_with_variables_returns_every_answer() -> None:
    proofs, _ = prove(FAMILY, PARENTS, parse_atom("Ancestor(ann, Who)"))
    assert [p.bindings for p in proofs] == [
        (("Who", "bob"),),
        (("Who", "cat"),),
        (("Who", "dan"),),
    ]
    assert all(str(p.tree.goal.args[1]) == dict(p.bindings)["Who"] for p in proofs)
    pairs, _ = prove(FAMILY, PARENTS, parse_atom("Ancestor(A, B)"))
    assert len(pairs) == 6
    assert len(prove(FAMILY, PARENTS, parse_atom("Ancestor(A, B)"), max_solutions=2)[0]) == 2


def test_unprovable_goal_fails_and_says_so() -> None:
    proofs, trace = prove(FAMILY, PARENTS, atom("Ancestor", "dan", "ann"))
    assert proofs == []
    assert any(isinstance(t, BackwardStep) and t.outcome == "fail" for t in trace)
    assert prove(FAMILY, PARENTS, atom("Unknown", "x"))[0] == []


def test_depth_limit_stops_a_left_recursive_rule() -> None:
    loop = [parse_rule("Path(X, Z) & Edge(Z, Y) -> Path(X, Y)", "left_rec")]
    proofs, trace = prove(loop, [atom("Edge", "a", "b")], atom("Path", "a", "b"), max_depth=6)
    assert proofs == []
    assert any(isinstance(t, BackwardStep) and t.outcome == "depth limit" for t in trace)


def test_backward_chaining_on_the_rescue_kb(shipped: dict[str, Scenario]) -> None:
    state = initial_state(shipped["showcase"])
    base = base_facts(state, reachable={"p1", "p2", "p3"}, urgent={"p2"})
    proofs, _ = prove(CORE_RULES, base, atom("RescueNow", "p2"))
    tree = proofs[0].tree
    assert rules_used(tree) == {
        "rescue_now", "eligible", "critical", "at_risk", "hot_unsafe", "hot_zone",
    }  # fmt: skip
    assert set(leaves(tree)) <= set(base)
    who, _ = prove(CORE_RULES, base, parse_atom("AtRisk(P)"))
    assert [p.bindings for p in who] == [(("P", "p2"),)]
    assert prove(CORE_RULES, base, atom("AtRisk", "p1"))[0] == []


# --- resolution ----------------------------------------------------------------------------------


def lit(text: str) -> Literal:
    return Literal(parse_atom(text.lstrip("~")), not text.startswith("~"))


def test_binary_resolution_rule() -> None:
    # propositional: (P v Q) and (~P v R) resolve to (Q v R)
    assert resolve((lit("P"), lit("Q")), (lit("~P"), lit("R"))) == [(lit("Q"), lit("R"))]
    # complementary unit clauses give the empty clause
    assert resolve((lit("P"),), (lit("~P"),)) == [()]
    assert show(()) == "□"
    # nothing complementary: no resolvent
    assert resolve((lit("P"),), (lit("Q"),)) == []
    # first-order: unification instantiates the rest of the clause
    out = resolve((lit("~Fire(X)"), lit("Unsafe(X)")), (lit("Fire(c1)"),))
    assert [show(c) for c in out] == ["Unsafe(c1)"]
    # duplicate literals merge (factoring by set semantics)
    assert resolve((lit("P"), lit("Q")), (lit("~P"), lit("Q"))) == [(lit("Q"),)]


def test_rule_to_cnf() -> None:
    clause = rule_clause(parse_rule("Adjacent(X, Y) & Fire(Y) -> Hot(X)"))
    assert show(clause) == "¬Adjacent(X, Y) ∨ ¬Fire(Y) ∨ Hot(X)"


def test_refutation_reaches_the_empty_clause_and_shows_each_resolvent() -> None:
    ref, trace = refute(FAMILY, PARENTS, atom("Ancestor", "ann", "cat"))
    assert ref.entailed
    assert ref.steps[0].clause == "¬Ancestor(ann, cat)" and ref.steps[0].parent is None
    assert ref.steps[-1].clause == "□"
    for prev, step in zip(ref.steps, ref.steps[1:], strict=False):
        assert step.parent == prev.clause  # a linear chain from the negated goal
        assert step.side_name in ("fact", "parent_anc", "trans_anc")
    assert ref.resolvents >= len(ref.steps) - 1
    assert all(isinstance(t, Resolved) for t in trace)


def test_refutation_fails_cleanly_for_a_non_theorem() -> None:
    ref, _ = refute(FAMILY, PARENTS, atom("Ancestor", "dan", "ann"))
    assert not ref.entailed and ref.steps == ()
    assert "saturated" in ref.reason
    gave_up, _ = refute(FAMILY, PARENTS, atom("Ancestor", "ann", "dan"), max_resolvents=1)
    assert not gave_up.entailed and "gave up" in gave_up.reason


def test_refutation_needs_a_ground_goal() -> None:
    with pytest.raises(ValueError, match="ground goal"):
        refute(FAMILY, PARENTS, parse_atom("Ancestor(ann, Who)"))


# --- the three methods agree ----------------------------------------------------------------------

GOALS = ["AtRisk", "Trapped", "Eligible", "Critical", "RescueNow", "Unavailable"]


def test_forward_backward_and_resolution_agree_on_every_shipped_scenario(
    shipped: dict[str, Scenario],
) -> None:
    for s in shipped.values():
        state = initial_state(s)
        ids = [p.id for p in s.people]
        base = base_facts(state, reachable=set(ids[:2]), urgent=set(ids))
        kb, _ = forward_chain(CORE_RULES, base)
        for pred in GOALS:
            for name in [*ids, *(e.id for e in s.exits)]:
                goal = atom(pred, name)
                holds = kb.holds(goal)
                assert bool(prove(CORE_RULES, base, goal)[0]) == holds, (s.name, goal)
                assert refute(CORE_RULES, base, goal)[0].entailed == holds, (s.name, goal)


@settings(max_examples=40, deadline=None)
@given(
    st.sets(st.tuples(st.sampled_from("abcde"), st.sampled_from("abcde")), max_size=8),
    st.sampled_from("abcde"),
    st.sampled_from("abcde"),
)
def test_prop_methods_agree_on_random_graphs(edges: set[tuple[str, str]], x: str, y: str) -> None:
    # Acyclic by construction (edges only go "up" the alphabet), so SLD terminates.
    base = [atom("Parent", a, b) for a, b in sorted(edges) if a < b]
    kb, _ = forward_chain(FAMILY, base)
    goal = atom("Ancestor", x, y)
    proofs, _ = prove(FAMILY, base, goal)
    assert bool(proofs) == kb.holds(goal) == refute(FAMILY, base, goal)[0].entailed
    for p in proofs:
        assert set(leaves(p.tree)) <= set(base) and rules_used(p.tree) <= {
            "parent_anc",
            "trans_anc",
        }
    answers = {
        dict(p.bindings)["W"] for p in prove(FAMILY, base, parse_atom(f"Ancestor({x}, W)"))[0]
    }
    assert answers == {
        str(f.args[1]) for f in kb.facts if f.pred == "Ancestor" and str(f.args[0]) == x
    }


def test_core_rule_proof_uses_only_kb_rules(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario(fire=[[3, 2]]))
    base = base_facts(state, {"p1"}, {"p1"})
    names = {r.name for r in CORE_RULES}
    for proof in prove(CORE_RULES, base, parse_atom("Unsafe(X)"))[0]:
        assert rules_used(proof.tree) <= names
