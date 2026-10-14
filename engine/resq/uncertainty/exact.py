"""Exact inference: enumeration and variable elimination. Both return P(query = True | evidence)."""

from dataclasses import dataclass, field
from itertools import product
from time import perf_counter

from ..trace import FactorEliminated, InferenceDone, Trace
from .bayesnet import Assignment, BayesNet


@dataclass(frozen=True)
class Exact:
    method: str
    query: str
    p_true: float
    work: int  # enumeration: joint entries summed; elimination: factor rows computed
    time_ms: float = field(default=0.0, compare=False)


def _check(bn: BayesNet, query: str, evidence: Assignment) -> None:
    unknown = [v for v in (query, *evidence) if v not in bn.nodes]
    if unknown:
        raise ValueError(f"unknown variable(s) {unknown}; the network has {list(bn.order)}")


def enumeration(bn: BayesNet, query: str, evidence: Assignment) -> tuple[Exact, Trace]:
    """Sum the full joint over the hidden variables: simple, exponential in their number."""
    _check(bn, query, evidence)
    t0 = perf_counter()
    work = 0

    def enumerate_all(names: tuple[str, ...], assignment: dict[str, bool]) -> float:
        nonlocal work
        if not names:
            work += 1
            return 1.0
        first, rest = names[0], names[1:]
        if first in assignment:
            return bn.p(first, assignment[first], assignment) * enumerate_all(rest, assignment)
        total = 0.0
        for value in (True, False):
            extended = {**assignment, first: value}
            total += bn.p(first, value, extended) * enumerate_all(rest, extended)
        return total

    if query in evidence:
        p = 1.0 if evidence[query] else 0.0
    else:
        weights = {v: enumerate_all(bn.order, {**evidence, query: v}) for v in (True, False)}
        total = weights[True] + weights[False]
        if total == 0:
            raise ValueError("the evidence has probability zero under this network")
        p = weights[True] / total
    result = Exact("enumeration", query, p, work, (perf_counter() - t0) * 1000)
    return result, [InferenceDone("enumeration", query, p, work)]


type Factor = tuple[tuple[str, ...], dict[tuple[bool, ...], float]]


def _node_factor(bn: BayesNet, name: str, evidence: Assignment) -> Factor:
    """The node's CPT as a factor over its unobserved variables."""
    scope = (*bn.nodes[name].parents, name)
    free = tuple(v for v in scope if v not in evidence)
    table = {}
    for values in product((True, False), repeat=len(free)):
        assignment = {**evidence, **dict(zip(free, values, strict=True))}
        table[values] = bn.p(name, assignment[name], assignment)
    return free, table


def _multiply(a: Factor, b: Factor) -> Factor:
    scope = (*a[0], *(v for v in b[0] if v not in a[0]))
    table = {}
    for values in product((True, False), repeat=len(scope)):
        row = dict(zip(scope, values, strict=True))
        table[values] = a[1][tuple(row[v] for v in a[0])] * b[1][tuple(row[v] for v in b[0])]
    return scope, table


def _sum_out(var: str, f: Factor) -> Factor:
    i = f[0].index(var)
    scope = (*f[0][:i], *f[0][i + 1 :])
    table: dict[tuple[bool, ...], float] = {}
    for values, p in f[1].items():
        key = (*values[:i], *values[i + 1 :])
        table[key] = table.get(key, 0.0) + p
    return scope, table


def elimination(bn: BayesNet, query: str, evidence: Assignment) -> tuple[Exact, Trace]:
    """Variable elimination: multiply only the factors that mention a hidden variable, sum it
    out, repeat. Same answer as enumeration without rebuilding the whole joint."""
    _check(bn, query, evidence)
    t0 = perf_counter()
    trace: Trace = []
    if query in evidence:
        p = 1.0 if evidence[query] else 0.0
        return Exact("elimination", query, p, 0, (perf_counter() - t0) * 1000), [
            InferenceDone("elimination", query, p, 0)
        ]
    factors = [_node_factor(bn, name, evidence) for name in bn.order]
    work = sum(len(f[1]) for f in factors)
    hidden = [v for v in reversed(bn.order) if v != query and v not in evidence]
    for var in hidden:  # leaves first: their factors are the smallest
        touching = [f for f in factors if var in f[0]]
        factors = [f for f in factors if var not in f[0]]
        joined = touching[0]
        for f in touching[1:]:
            joined = _multiply(joined, f)
            work += len(joined[1])
        summed = _sum_out(var, joined)
        work += len(summed[1])
        trace.append(FactorEliminated(var, joined[0], len(joined[1])))
        factors.append(summed)
    final = factors[0]
    for f in factors[1:]:
        final = _multiply(final, f)
        work += len(final[1])
    # every remaining factor is over the query alone (or constant)
    weights = {True: 0.0, False: 0.0}
    for values, p in final[1].items():
        row = dict(zip(final[0], values, strict=True))
        weights[row[query]] += p
    total = weights[True] + weights[False]
    if total == 0:
        raise ValueError("the evidence has probability zero under this network")
    p = weights[True] / total
    trace.append(InferenceDone("elimination", query, p, work))
    return Exact("elimination", query, p, work, (perf_counter() - t0) * 1000), trace
