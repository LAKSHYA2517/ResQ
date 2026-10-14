"""Approximate inference by sampling. Seeded: the same seed gives the same estimate."""

from collections.abc import Callable
from dataclasses import dataclass, field
from random import Random
from time import perf_counter

from ..trace import InferenceDone, Trace
from .bayesnet import Assignment, BayesNet
from .exact import _check


@dataclass(frozen=True)
class Sampled:
    method: str
    query: str
    p_true: float | None  # None when no sample was consistent with the evidence
    samples: int  # samples drawn
    used: float  # rejection: samples kept; weighting: total weight; Gibbs: samples counted
    curve: tuple[tuple[int, float], ...]  # (samples drawn so far, estimate so far)
    time_ms: float = field(default=0.0, compare=False)


def _checkpoints(n: int, points: int = 60) -> set[int]:
    """Roughly log-spaced sample counts at which the running estimate is recorded."""
    out = {n}
    x = 1.0
    while x < n:
        out.add(int(x))
        x = max(x + 1, x * (n ** (1 / points)))
    return out


def _prior_sample(bn: BayesNet, rng: Random) -> dict[str, bool]:
    sample: dict[str, bool] = {}
    for name in bn.order:
        sample[name] = rng.random() < bn.p(name, True, sample)
    return sample


def _run(
    method: str,
    query: str,
    n: int,
    draw: Callable[[], tuple[bool, float]],
) -> tuple[Sampled, Trace]:
    """Shared loop: ``draw`` returns (query value, weight of this sample)."""
    t0 = perf_counter()
    marks = _checkpoints(n)
    hit = total = 0.0
    curve: list[tuple[int, float]] = []
    for i in range(1, n + 1):
        value, weight = draw()
        total += weight
        if value:
            hit += weight
        if i in marks and total > 0:
            curve.append((i, hit / total))
    p = hit / total if total > 0 else None
    result = Sampled(method, query, p, n, total, tuple(curve), (perf_counter() - t0) * 1000)
    return result, [InferenceDone(method, query, p, n)]


def rejection(
    bn: BayesNet, query: str, evidence: Assignment, n: int, rng: Random
) -> tuple[Sampled, Trace]:
    """Sample the whole network from the prior; throw away samples that contradict the
    evidence. Wasteful when the evidence is unlikely."""
    _check(bn, query, evidence)

    def draw() -> tuple[bool, float]:
        s = _prior_sample(bn, rng)
        keep = all(s[k] == v for k, v in evidence.items())
        return s[query], 1.0 if keep else 0.0

    return _run("rejection", query, n, draw)


def likelihood_weighting(
    bn: BayesNet, query: str, evidence: Assignment, n: int, rng: Random
) -> tuple[Sampled, Trace]:
    """Fix the evidence variables and weight each sample by how likely that evidence was given
    its sampled parents. No sample is wasted."""
    _check(bn, query, evidence)

    def draw() -> tuple[bool, float]:
        sample: dict[str, bool] = {}
        weight = 1.0
        for name in bn.order:
            if name in evidence:
                sample[name] = evidence[name]
                weight *= bn.p(name, evidence[name], sample)
            else:
                sample[name] = rng.random() < bn.p(name, True, sample)
        return sample[query], weight

    return _run("likelihood_weighting", query, n, draw)


def gibbs(
    bn: BayesNet, query: str, evidence: Assignment, n: int, rng: Random, burn_in: int = 100
) -> tuple[Sampled, Trace]:
    """Markov chain Monte Carlo: start anywhere consistent with the evidence, then repeatedly
    resample one hidden variable given its Markov blanket. Samples are correlated, and the first
    ``burn_in`` sweeps are discarded."""
    _check(bn, query, evidence)
    hidden = [v for v in bn.order if v not in evidence]
    state = {**{v: rng.random() < 0.5 for v in hidden}, **evidence}
    kids = {v: bn.children(v) for v in hidden}

    def sweep() -> None:
        for var in hidden:
            weights = []
            for value in (True, False):
                state[var] = value
                w = bn.p(var, value, state)
                for child in kids[var]:
                    w *= bn.p(child, state[child], state)
                weights.append(w)
            total = weights[0] + weights[1]
            state[var] = rng.random() < (weights[0] / total if total > 0 else 0.5)

    for _ in range(burn_in if hidden else 0):
        sweep()

    def draw() -> tuple[bool, float]:
        sweep()
        return state[query], 1.0

    return _run("gibbs", query, n, draw)


SAMPLERS = {"rejection": rejection, "likelihood_weighting": likelihood_weighting, "gibbs": gibbs}
