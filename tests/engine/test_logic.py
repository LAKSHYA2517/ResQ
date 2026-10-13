from collections.abc import Callable
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from resq.logic.forward import forward_chain, solutions
from resq.logic.kb import KB, FactIndex
from resq.logic.rules import CORE_RULES, base_facts
from resq.logic.terms import (
    Atom,
    Const,
    Fn,
    ParseError,
    Rule,
    Term,
    Var,
    atom,
    is_ground,
    parse_atom,
    parse_rule,
    parse_rules,
    parse_term,
    variables,
)
from resq.logic.unify import compose, substitute, substitute_atom, unify, unify_atoms
from resq.trace import FixpointReached, RuleFired
from resq.world.grid import cell_name, name_cell
from resq.world.scenarios import Scenario, initial_state
from resq.world.state import Status

X, Y, Z = Var("X"), Var("Y"), Var("Z")
a, b = Const("a"), Const("b")


# --- syntax ---------------------------------------------------------------------------------


def test_parse_atom_distinguishes_variables_constants_and_functions() -> None:
    parsed = parse_atom("Person(P, c3_4, f(X, a))")
    assert parsed == Atom("Person", (Var("P"), Const("c3_4"), Fn("f", (X, a))))
    assert str(parsed) == "Person(P, c3_4, f(X, a))"
    assert parse_atom("HandsFree") == Atom("HandsFree")
    assert str(Atom("HandsFree")) == "HandsFree"
    assert parse_term("p1") == Const("p1") and parse_term("Who") == Var("Who")


def test_parse_rule_round_trips() -> None:
    rule = parse_rule("Adjacent(X, Y) & Fire(Y) -> Hot(X)", "hot_zone")
    assert rule.name == "hot_zone" and len(rule.body) == 2
    assert str(rule) == "Adjacent(X, Y) & Fire(Y) -> Hot(X)"
    assert parse_rule(str(rule), "hot_zone") == rule
    assert parse_rule("A(X) -> B(X)").name == "A(X) -> B(X)"


@pytest.mark.parametrize(
    "text", ["", "Fire(", "Fire(X", "Fire(X,)", "Fire(X) Fire(Y)", "Fire(X) -> ", "Fire$(X)", "(X)"]
)
def test_parse_errors(text: str) -> None:
    with pytest.raises(ParseError):
        parse_rule(text) if "->" in text else parse_atom(text)


def test_rule_head_variables_must_occur_in_body() -> None:
    with pytest.raises(ValueError, match="do not occur in the body"):
        parse_rule("Fire(X) -> Hot(Y)")


def test_parse_rules_skips_blanks_and_comments() -> None:
    rules = parse_rules(
        "\n  r1: A(X) -> B(X)   # comment\n\n  # only a comment\n  r2: B(X) -> C(X)\n"
    )
    assert [r.name for r in rules] == ["r1", "r2"]


def test_variables_and_groundness() -> None:
    t = Fn("f", (X, Fn("g", (Y, a))))
    assert variables(t) == {X, Y}
    assert not is_ground(t) and is_ground(atom("Fire", "c1_1"))


def test_cell_names_round_trip() -> None:
    assert cell_name((3, 14)) == "c3_14" and name_cell("c3_14") == (3, 14)


# --- unification ------------------------------------------------------------------------------


def test_unify_basics() -> None:
    assert unify(X, a) == {X: a}
    assert unify(a, X) == {X: a}
    assert unify(a, a) == {}
    assert unify(a, b) is None
    assert unify(Fn("f", (X, b)), Fn("f", (a, Y))) == {X: a, Y: b}
    assert unify(Fn("f", (X,)), Fn("g", (X,))) is None
    assert unify(Fn("f", (X,)), Fn("f", (X, Y))) is None
    assert unify(a, Fn("f", (X,))) is None


def test_unify_chains_bindings_and_stays_idempotent() -> None:
    s = unify(Fn("f", (X, Y)), Fn("f", (Y, a)))
    assert s == {X: a, Y: a}


def test_occurs_check_rejects_infinite_terms() -> None:
    assert unify(X, Fn("f", (X,))) is None
    assert unify(Fn("f", (X, X)), Fn("f", (Y, Fn("g", (Y,))))) is None


def test_unify_does_not_mutate_its_input() -> None:
    s: dict[Var, Term] = {X: a}
    out = unify(Y, b, s)
    assert s == {X: a} and out == {X: a, Y: b}


def test_unify_atoms() -> None:
    assert unify_atoms(parse_atom("Person(P, X)"), atom("Person", "p1", "c1_1")) == {
        Var("P"): Const("p1"),
        X: Const("c1_1"),
    }
    assert unify_atoms(parse_atom("Person(P, P)"), atom("Person", "p1", "c1_1")) is None
    assert unify_atoms(parse_atom("Fire(X)"), atom("Hot", "c1_1")) is None
    assert unify_atoms(parse_atom("Fire(X)"), atom("Fire", "c1_1", "c1_2")) is None


TERMS = st.recursive(
    st.sampled_from([a, b, X, Y, Z]),
    lambda kids: st.builds(
        Fn, st.sampled_from(["f", "g"]), st.lists(kids, min_size=1, max_size=2).map(tuple)
    ),
    max_leaves=6,
)


@settings(max_examples=400, deadline=None)
@given(TERMS, TERMS)
def test_prop_unifier_really_unifies_and_is_idempotent(x: Term, y: Term) -> None:
    s = unify(x, y)
    if s is None:
        if is_ground(x) and is_ground(y):
            assert x != y
        return
    assert substitute(x, s) == substitute(y, s)
    once = substitute(x, s)
    assert substitute(once, s) == once  # idempotent
    for v, t in s.items():
        assert v not in variables(t)  # the occurs check held


@settings(max_examples=300, deadline=None)
@given(TERMS, TERMS, TERMS, TERMS, TERMS)
def test_prop_compose_is_apply_then_apply(t: Term, x1: Term, y1: Term, x2: Term, y2: Term) -> None:
    s1, s2 = unify(x1, y1), unify(x2, y2)
    if s1 is None or s2 is None:
        return
    assert substitute(t, compose(s1, s2)) == substitute(substitute(t, s1), s2)


# --- forward chaining ---------------------------------------------------------------------------

FAMILY = parse_rules(
    """
    parent_anc:  Parent(X, Y) -> Ancestor(X, Y)
    trans_anc:   Parent(X, Y) & Ancestor(Y, Z) -> Ancestor(X, Z)
    """
)
PARENTS = [atom("Parent", "ann", "bob"), atom("Parent", "bob", "cat"), atom("Parent", "cat", "dan")]


def test_forward_chaining_reaches_the_fixpoint_level_by_level() -> None:
    kb, trace = forward_chain(FAMILY, PARENTS)
    derived = {str(f) for f in kb.derived}
    assert derived == {
        "Ancestor(ann, bob)",
        "Ancestor(bob, cat)",
        "Ancestor(cat, dan)",
        "Ancestor(ann, cat)",
        "Ancestor(bob, dan)",
        "Ancestor(ann, dan)",
    }
    assert kb.derived[atom("Ancestor", "ann", "bob")].iteration == 1
    assert kb.derived[atom("Ancestor", "ann", "cat")].iteration == 2
    assert kb.derived[atom("Ancestor", "ann", "dan")].iteration == 3
    fired = [t for t in trace if isinstance(t, RuleFired)]
    assert len(fired) == len(kb.derived)  # each fact stored once: no duplicates
    assert trace[-1] == FixpointReached(4, 3, 6)  # the 4th pass derives nothing


def test_provenance_names_rule_bindings_and_premises() -> None:
    kb, _ = forward_chain(FAMILY, PARENTS)
    d = kb.derived[atom("Ancestor", "ann", "cat")]
    assert d.rule == "trans_anc"
    assert d.bindings == (("X", "ann"), ("Y", "bob"), ("Z", "cat"))
    assert d.premises == (atom("Parent", "ann", "bob"), atom("Ancestor", "bob", "cat"))
    chain = kb.why(atom("Ancestor", "ann", "dan"))
    assert chain[-1].fact == atom("Ancestor", "ann", "dan")
    known = set(kb.base)
    for step in chain:  # premises always come before the conclusions that use them
        assert set(step.premises) <= known
        known.add(step.fact)
    assert kb.why(PARENTS[0]) == () and kb.why(atom("Ancestor", "dan", "ann")) == ()


def test_forward_chaining_is_idempotent() -> None:
    kb, _ = forward_chain(FAMILY, PARENTS)
    again, trace = forward_chain(FAMILY, list(kb.facts))
    assert not again.derived and set(again.facts) == set(kb.facts)
    assert trace == [FixpointReached(1, 9, 0)]


def test_ask_and_holds() -> None:
    kb, _ = forward_chain(FAMILY, PARENTS)
    assert kb.holds(atom("Ancestor", "ann", "dan")) and not kb.holds(atom("Ancestor", "dan", "ann"))
    answers = kb.ask(parse_atom("Ancestor(ann, Who)"))
    assert sorted(str(s[Var("Who")]) for s in answers) == ["bob", "cat", "dan"]
    assert kb.constants("Parent") == ["ann", "bob", "cat"]


def test_join_starts_from_the_smallest_relation() -> None:
    facts = FactIndex(
        [atom("Adjacent", f"c{i}", f"c{i + 1}") for i in range(200)] + [atom("Fire", "c7")]
    )
    body = parse_rule("Adjacent(X, Y) & Fire(Y) -> Hot(X)").body
    assert facts.candidates(substitute_atom(body[0], {Y: Const("c7")})) == [
        atom("Adjacent", "c6", "c7")
    ]
    found = list(solutions(body, facts))
    assert len(found) == 1
    assert found[0][1] == (atom("Adjacent", "c6", "c7"), atom("Fire", "c7"))  # body order kept


def test_fact_index_is_a_set() -> None:
    idx = FactIndex()
    assert idx.add(atom("Fire", "c1")) and not idx.add(atom("Fire", "c1"))
    assert len(idx) == 1 and atom("Fire", "c1") in idx


def test_kb_drops_duplicate_base_facts() -> None:
    assert len(KB((), [atom("Fire", "c1"), atom("Fire", "c1")]).base) == 1


def test_rule_str_and_dataclass() -> None:
    r = Rule("r", (parse_atom("A(X)"),), parse_atom("B(X)"))
    assert str(r) == "A(X) -> B(X)"


# --- the rescue rules against a real world state ------------------------------------------------


def ids(kb: KB, pred: str) -> set[str]:
    return set(kb.constants(pred))


def test_core_rules_on_a_state(make_scenario: Callable[..., Scenario]) -> None:
    s = make_scenario(
        fire=[[2, 2], [4, 3]],
        people=[
            {"id": "near_fire", "pos": [2, 3], "urgency": 4},
            {"id": "calm_hot", "pos": [1, 2], "urgency": 0},
            {"id": "safe", "pos": [0, 4], "urgency": 5},
        ],
        exits=[{"id": "e1", "pos": [4, 4]}, {"id": "e2", "pos": [0, 0], "available": False}],
        agent=[1, 0],
    )
    state = initial_state(s)
    kb, _ = forward_chain(
        CORE_RULES, base_facts(state, reachable={"near_fire", "safe"}, urgent={"near_fire", "safe"})
    )
    assert {name_cell(c) for c in ids(kb, "Hot")} - state.fire == state.hot
    assert {name_cell(c) for c in ids(kb, "Unsafe")} == state.hot | state.fire
    assert ids(kb, "AtRisk") == {"near_fire", "calm_hot"}
    assert ids(kb, "Critical") == {"near_fire"}  # at risk AND urgent
    assert ids(kb, "Eligible") == {"near_fire", "safe"}  # waiting AND reachable
    assert ids(kb, "RescueNow") == {"near_fire"}
    assert ids(kb, "Unavailable") == {"e2"}  # blocked
    assert ids(kb, "Trapped") == set()
    d = kb.derived[atom("AtRisk", "near_fire")]
    assert d.rule == "at_risk" and d.premises[0] == atom("Person", "near_fire", "c2_3")


def test_trapped_person_and_burning_exit(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario())
    burning = replace(state, fire=frozenset({(3, 1), (4, 4)}))
    burning = burning.with_person(replace(burning.person("p1"), status=Status.TRAPPED))
    kb, _ = forward_chain(CORE_RULES, base_facts(burning, reachable=set(), urgent=set()))
    assert ids(kb, "Trapped") == {"p1"}
    assert ids(kb, "Unavailable") == {"e1"}
    assert ids(kb, "Eligible") == set()  # not Waiting, so never eligible
    chain = kb.why(atom("Trapped", "p1"))
    assert [str(p) for p in chain[0].premises] == ["Person(p1, c3_1)", "Fire(c3_1)"]


def test_base_facts_reflect_agent_and_evacuees(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario())
    carried = replace(state, agent=replace(state.agent, carrying="p1")).with_person(
        replace(state.person("p1"), status=Status.CARRIED, pos=(0, 0))
    )
    facts = set(base_facts(carried, set(), set()))
    assert {atom("AgentAt", "c0_0"), atom("Carrying", "p1"), atom("Person", "p1", "c0_0")} <= facts
    assert atom("Waiting", "p1") not in facts
    gone = state.with_person(replace(state.person("p1"), status=Status.EVACUATED))
    facts = set(base_facts(gone, set(), set()))
    assert atom("Evacuated", "p1") in facts and not any(f.pred == "Person" for f in facts)


def test_adjacency_skips_walls(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario(terrain=[".#...", ".....", ".....", ".....", "....."]))
    adj = {f for f in base_facts(state, set(), set()) if f.pred == "Adjacent"}
    assert atom("Adjacent", "c0_0", "c1_0") in adj and atom("Adjacent", "c1_0", "c0_0") in adj
    assert not any("c0_1" in map(str, f.args) for f in adj)


def test_forward_chaining_on_every_shipped_scenario_is_a_fixpoint(
    shipped: dict[str, Scenario],
) -> None:
    for s in shipped.values():
        state = initial_state(s)
        kb, _ = forward_chain(CORE_RULES, base_facts(state, {p.id for p in s.people}, set()))
        again, _ = forward_chain(CORE_RULES, list(kb.facts))
        assert not again.derived, s.name
        assert {name_cell(c) for c in ids(kb, "Hot")} - state.fire == state.hot, s.name
        for d in kb.derived.values():  # every premise is itself known
            assert all(kb.holds(p) for p in d.premises)
