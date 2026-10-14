"""Backward chaining (SLD resolution, depth-first, left to right) with proof trees.

Starts from the goal and works back to base facts. A proof uses only the KB's rules and base
facts: nothing derived by forward chaining is consulted, so the two methods check each other.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import count

from ..trace import BackwardStep, Trace
from .kb import FactIndex
from .terms import Atom, Fn, Rule, Term, Var, variables
from .unify import Subst, substitute, substitute_atom, unify_atoms

MAX_DEPTH = 30


@dataclass(frozen=True)
class ProofNode:
    goal: Atom  # fully instantiated
    rule: str | None  # None: the goal is a base fact
    children: tuple["ProofNode", ...] = ()


@dataclass(frozen=True)
class Proof:
    bindings: tuple[tuple[str, str], ...]  # the query's variables -> values
    tree: ProofNode


def _rename(rule: Rule, n: int) -> Rule:
    """Standardise apart: fresh variable names for each use of a rule."""

    def term(t: Term) -> Term:
        if isinstance(t, Var):
            return Var(f"{t.name}_{n}")
        if isinstance(t, Fn):
            return Fn(t.name, tuple(term(a) for a in t.args))
        return t

    def atom(a: Atom) -> Atom:
        return Atom(a.pred, tuple(term(t) for t in a.args))

    return Rule(rule.name, tuple(atom(b) for b in rule.body), atom(rule.head))


def _ground(node: ProofNode, s: Subst) -> ProofNode:
    return ProofNode(
        substitute_atom(node.goal, s), node.rule, tuple(_ground(c, s) for c in node.children)
    )


def prove(
    rules: Iterable[Rule],
    base: Iterable[Atom],
    goal: Atom,
    max_solutions: int = 50,
    max_depth: int = MAX_DEPTH,
) -> tuple[list[Proof], Trace]:
    """Every distinct answer to ``goal`` (up to ``max_solutions``), each with one proof tree.

    To prove a goal: match it against a base fact, or pick a rule whose head unifies with it
    and prove every atom of that rule's body in order. Rule order and fact order are fixed, so
    the first proof found is always the same one.
    """
    rules = tuple(rules)
    facts = FactIndex(base)
    fresh = count(1)
    trace: Trace = []

    def solve(g: Atom, s: Subst, depth: int) -> Iterator[tuple[Subst, ProofNode]]:
        g = substitute_atom(g, s)
        if depth > max_depth:
            trace.append(BackwardStep(depth, str(g), "depth limit"))
            return
        proved = False
        for fact in facts.candidates(g):
            s2 = unify_atoms(g, fact, s)
            if s2 is not None:
                proved = True
                trace.append(BackwardStep(depth, str(fact), "fact"))
                yield s2, ProofNode(fact, None)
        for rule in rules:
            if rule.head.pred != g.pred:
                continue
            r = _rename(rule, next(fresh))
            s2 = unify_atoms(r.head, g, s)
            if s2 is None:
                continue
            trace.append(BackwardStep(depth, str(g), f"try {rule.name}"))
            for s3, children in solve_all(r.body, s2, depth + 1):
                proved = True
                yield s3, ProofNode(substitute_atom(r.head, s3), rule.name, children)
        if not proved:
            trace.append(BackwardStep(depth, str(g), "fail"))

    def solve_all(
        body: tuple[Atom, ...], s: Subst, depth: int
    ) -> Iterator[tuple[Subst, tuple[ProofNode, ...]]]:
        if not body:
            yield s, ()
            return
        for s2, first in solve(body[0], s, depth):
            for s3, rest in solve_all(body[1:], s2, depth):
                yield s3, (first, *rest)

    query_vars = sorted(variables(goal), key=lambda v: v.name)
    proofs: dict[tuple[tuple[str, str], ...], Proof] = {}
    for s, tree in solve(goal, {}, 0):
        bindings = tuple((v.name, str(substitute(v, s))) for v in query_vars)
        if bindings not in proofs:
            proofs[bindings] = Proof(bindings, _ground(tree, s))
            if len(proofs) >= max_solutions:
                break
    return list(proofs.values()), trace
