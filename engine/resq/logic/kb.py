"""Knowledge base: base facts + Horn rules + derived facts with provenance.

Closed-world assumption: a fact that is neither a base fact nor derivable is false. Rules never
contain negation; "not Unavailable(e1)" is only ever asked as a *query* (absence from the KB).
The KB is rebuilt from the world state every tick, so no stale fact can survive.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from .terms import Atom, Const, Rule, Term
from .unify import Subst, unify_atoms


@dataclass(frozen=True)
class Derivation:
    """Why a derived fact holds: the rule that fired, its bindings and the premises it used."""

    fact: Atom
    rule: str
    bindings: tuple[tuple[str, str], ...]  # (variable, value) sorted by variable
    premises: tuple[Atom, ...]  # in rule-body order
    iteration: int  # forward-chaining pass that first produced the fact


class FactIndex:
    """Insertion-ordered set of ground atoms, indexed by predicate and by constant argument."""

    def __init__(self, facts: Iterable[Atom] = ()) -> None:
        self._all: dict[Atom, None] = {}
        self._by_pred: dict[str, list[Atom]] = {}
        self._by_arg: dict[tuple[str, int, Term], list[Atom]] = {}
        for f in facts:
            self.add(f)

    def add(self, fact: Atom) -> bool:
        if fact in self._all:
            return False
        self._all[fact] = None
        self._by_pred.setdefault(fact.pred, []).append(fact)
        for i, arg in enumerate(fact.args):
            self._by_arg.setdefault((fact.pred, i, arg), []).append(fact)
        return True

    def __contains__(self, fact: object) -> bool:
        return fact in self._all

    def __iter__(self) -> Iterator[Atom]:
        return iter(self._all)

    def __len__(self) -> int:
        return len(self._all)

    def candidates(self, pattern: Atom) -> list[Atom]:
        """Facts that could match ``pattern``: the smallest index bucket available."""
        best = self._by_pred.get(pattern.pred, [])
        for i, arg in enumerate(pattern.args):
            if isinstance(arg, Const):
                bucket = self._by_arg.get((pattern.pred, i, arg), [])
                if len(bucket) < len(best):
                    best = bucket
        return best


class KB:
    def __init__(self, rules: Iterable[Rule], base: Iterable[Atom]) -> None:
        self.rules = tuple(rules)
        self.base = tuple(dict.fromkeys(base))
        self.facts = FactIndex(self.base)
        self.derived: dict[Atom, Derivation] = {}

    def holds(self, fact: Atom) -> bool:
        return fact in self.facts

    def ask(self, pattern: Atom) -> list[Subst]:
        """Every substitution under which ``pattern`` matches a known fact."""
        out = []
        for fact in self.facts.candidates(pattern):
            s = unify_atoms(pattern, fact)
            if s is not None:
                out.append(s)
        return out

    def constants(self, pred: str) -> list[str]:
        """First arguments of all facts with this predicate, e.g. the ids with ``Eligible``."""
        return [str(f.args[0]) for f in self.facts.candidates(Atom(pred))]

    def why(self, fact: Atom) -> tuple[Derivation, ...]:
        """The derivations supporting ``fact``, premises before conclusions. Empty for a base
        fact (it holds because the world state says so) or for something that does not hold."""
        out: dict[Atom, Derivation] = {}

        def visit(f: Atom) -> None:
            d = self.derived.get(f)
            if d is None or f in out:
                return
            for premise in d.premises:
                visit(premise)
            out[f] = d

        visit(fact)
        return tuple(out.values())
