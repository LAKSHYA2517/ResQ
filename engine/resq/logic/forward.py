"""Forward chaining to a fixpoint, recording provenance for every derived fact."""

from collections.abc import Iterable, Iterator

from ..trace import FixpointReached, RuleFired, Trace
from .kb import KB, Derivation, FactIndex
from .terms import Atom, Rule
from .unify import Subst, substitute_atom, unify_atoms


def solutions(
    body: tuple[Atom, ...], facts: FactIndex, s: Subst | None = None
) -> Iterator[tuple[Subst, tuple[Atom, ...]]]:
    """Every way to satisfy all body atoms from ``facts``: ``(bindings, premises in body order)``.

    Join order is chosen greedily: at each step match the body atom with the fewest candidate
    facts under the current bindings (so ``Adjacent(X,Y) & Fire(Y)`` starts from the few Fire
    facts, not the many Adjacent ones). Ties go to the earlier atom, so it is deterministic.
    """

    def solve(
        pending: tuple[int, ...], s: Subst, chosen: dict[int, Atom]
    ) -> Iterator[tuple[Subst, tuple[Atom, ...]]]:
        if not pending:
            yield s, tuple(chosen[i] for i in range(len(body)))
            return
        patterns = {i: substitute_atom(body[i], s) for i in pending}
        best = min(pending, key=lambda i: len(facts.candidates(patterns[i])))
        rest = tuple(i for i in pending if i != best)
        for fact in facts.candidates(patterns[best]):
            s2 = unify_atoms(patterns[best], fact, s)
            if s2 is not None:
                yield from solve(rest, s2, {**chosen, best: fact})

    return solve(tuple(range(len(body))), {} if s is None else s, {})


def forward_chain(rules: Iterable[Rule], base: Iterable[Atom]) -> tuple[KB, Trace]:
    """Apply every rule to everything known until a pass derives nothing new.

    Each pass only uses facts known at its start, so the trace reads level by level. A fact is
    stored once, with the first derivation that produced it.
    """
    # ponytail: naive evaluation (each pass re-joins all facts). Fine for a 30x30 grid and ten
    # rules with the argument index; switch to semi-naive if the rule base grows a lot.
    kb = KB(rules, base)
    trace: Trace = []
    iteration = 0
    while True:
        iteration += 1
        new: dict[Atom, Derivation] = {}
        for rule in kb.rules:
            for s, premises in solutions(rule.body, kb.facts):
                head = substitute_atom(rule.head, s)
                if head in kb.facts or head in new:
                    continue
                bindings = tuple(sorted((v.name, str(t)) for v, t in s.items()))
                new[head] = Derivation(head, rule.name, bindings, premises, iteration)
                trace.append(
                    RuleFired(iteration, rule.name, str(head), bindings, tuple(map(str, premises)))
                )
        if not new:
            break
        for fact, derivation in new.items():
            kb.facts.add(fact)
            kb.derived[fact] = derivation
    trace.append(FixpointReached(iteration, len(kb.base), len(kb.derived)))
    return kb, trace
