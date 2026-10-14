"""Resolution refutation: to show KB |= goal, add the negated goal and derive the empty clause.

Clauses are disjunctions of literals. A Horn rule ``A & B -> C`` is the clause
``~A | ~B | C``; a fact is a unit clause. ``resolve`` is the general binary resolution rule
(with unification, so it covers the propositional case and first-order clauses alike).

``refute`` uses the set-of-support strategy with input resolution on the leftmost literal:
every resolvent descends from the negated goal and is resolved against a KB clause. That
strategy is complete for Horn clauses, which is all this KB contains, and it keeps the search
to the facts relevant to the query instead of resolving the whole grid against itself.
"""

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import count

from ..trace import Resolved, Trace
from .kb import FactIndex
from .terms import Atom, Fn, Rule, Term, Var, is_ground
from .unify import Subst, substitute_atom, unify_atoms


@dataclass(frozen=True)
class Literal:
    atom: Atom
    positive: bool = True

    def __str__(self) -> str:
        return str(self.atom) if self.positive else f"¬{self.atom}"


type Clause = tuple[Literal, ...]  # ordered, no duplicates; () is the empty clause


def show(clause: Clause) -> str:
    return " ∨ ".join(map(str, clause)) if clause else "□"


def rule_clause(rule: Rule) -> Clause:
    """CNF of a Horn rule: the negated body atoms, then the head."""
    return (*(Literal(b, False) for b in rule.body), Literal(rule.head, True))


def _apply(clause: Iterable[Literal], s: Subst) -> Clause:
    out: dict[Literal, None] = {}
    for lit in clause:
        out[Literal(substitute_atom(lit.atom, s), lit.positive)] = None
    return tuple(out)


def _rename(clause: Clause, n: int) -> Clause:
    def term(t: Term) -> Term:
        if isinstance(t, Var):
            return Var(f"{t.name}_{n}")
        if isinstance(t, Fn):
            return Fn(t.name, tuple(term(a) for a in t.args))
        return t

    return tuple(
        Literal(Atom(lit.atom.pred, tuple(term(t) for t in lit.atom.args)), lit.positive)
        for lit in clause
    )


def resolve(c1: Clause, c2: Clause) -> list[Clause]:
    """All binary resolvents of two clauses (assumed to share no variables)."""
    out: list[Clause] = []
    for i, a in enumerate(c1):
        for j, b in enumerate(c2):
            if a.positive == b.positive:
                continue
            s = unify_atoms(a.atom, b.atom)
            if s is not None:
                rest = (*c1[:i], *c1[i + 1 :], *c2[:j], *c2[j + 1 :])
                resolvent = _apply(rest, s)
                if resolvent not in out:
                    out.append(resolvent)
    return out


@dataclass(frozen=True)
class Step:
    """One line of the refutation: ``clause`` was obtained by resolving ``parent`` with
    ``side`` (a KB fact or rule). The first step is the negated goal and has neither."""

    clause: str
    parent: str | None
    side: str | None
    side_name: str | None  # rule name, or "fact"


@dataclass(frozen=True)
class Refutation:
    goal: str
    entailed: bool
    steps: tuple[Step, ...]  # the chain from the negated goal to the empty clause
    resolvents: int  # resolvents generated in total while searching
    reason: str = ""


def refute(
    rules: Iterable[Rule], base: Iterable[Atom], goal: Atom, max_resolvents: int = 20_000
) -> tuple[Refutation, Trace]:
    """Refute ``KB & ~goal`` for a ground goal."""
    if not is_ground(goal):
        raise ValueError(f"resolution refutation needs a ground goal, got {goal}")
    rules = tuple(rules)
    facts = FactIndex(base)
    fresh = count(1)
    trace: Trace = []
    start: Clause = (Literal(goal, False),)
    # clause -> (parent clause, side clause text, side name)
    origin: dict[Clause, tuple[Clause, str, str] | None] = {start: None}
    queue: deque[Clause] = deque([start])
    generated = 0
    empty: Clause = ()

    def chain() -> tuple[Step, ...]:
        steps: list[Step] = []
        c: Clause = empty
        while True:
            how = origin[c]
            if how is None:
                steps.append(Step(show(c), None, None, None))
                break
            steps.append(Step(show(c), show(how[0]), how[1], how[2]))
            c = how[0]
        return tuple(reversed(steps))

    while queue:
        clause = queue.popleft()
        selected = clause[0]  # set of support only ever holds negative literals here
        sides: list[tuple[Clause, str]] = [
            ((Literal(f),), "fact") for f in facts.candidates(selected.atom)
        ]
        sides += [
            (_rename(rule_clause(r), next(fresh)), r.name)
            for r in rules
            if r.head.pred == selected.atom.pred
        ]
        for side, name in sides:
            s = unify_atoms(selected.atom, side[-1].atom)
            if s is None:
                continue
            # input resolution on the selected literal: side's body literals come first
            resolvent = _apply((*side[:-1], *clause[1:]), s)
            generated += 1
            if resolvent in origin:
                continue
            origin[resolvent] = (clause, show(side), name)
            trace.append(Resolved(show(clause), show(side), show(resolvent)))
            if resolvent == empty:
                return Refutation(str(goal), True, chain(), generated), trace
            if generated >= max_resolvents:
                reason = f"gave up after {generated} resolvents"
                return Refutation(str(goal), False, (), generated, reason), trace
            queue.append(resolvent)
    reason = (
        "the set of support is saturated without reaching the empty clause, so the goal does"
        " not follow from the KB (closed world: it is false)"
    )
    return Refutation(str(goal), False, (), generated, reason), trace
