"""Priority function: who to rescue next, with a human-readable breakdown.

    Priority(P)   = w_r * Risk(P) + w_u * Urgency(P, t) - w_d * PathCost(agent -> P)
    Urgency(P, t) = min(cap, base_urgency + gamma * ticks_waiting)

These are simulation values chosen to make the trade-off visible. They are not medical triage.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from ..world.scenarios import Weights


@dataclass(frozen=True)
class PriorityScore:
    person_id: str
    risk: float
    urgency: float
    path_cost: float
    score: float
    breakdown: str  # e.g. "p2: 5×4 + 3×3 − 1×10 = 19"


@dataclass(frozen=True)
class Choice:
    target: str | None
    switched: bool  # True when an existing target was replaced
    reason: str


def urgency(base: float, ticks_waiting: int, w: Weights) -> float:
    return min(w.urgency_cap, base + w.gamma * ticks_waiting)


def score(person_id: str, risk: float, urg: float, path_cost: float, w: Weights) -> PriorityScore:
    value = w.w_r * risk + w.w_u * urg - w.w_d * path_cost
    text = (
        f"{person_id}: {w.w_r:g}×{risk:g} + {w.w_u:g}×{urg:g} − {w.w_d:g}×{path_cost:g} = {value:g}"
    )
    return PriorityScore(person_id, risk, urg, path_cost, value, text)


def rank(scores: Iterable[PriorityScore]) -> tuple[PriorityScore, ...]:
    """Highest score first. Ties: lower path cost, then id."""
    return tuple(sorted(scores, key=lambda s: (-s.score, s.path_cost, s.person_id)))


def choose_target(ranked: tuple[PriorityScore, ...], current: str | None, delta: float) -> Choice:
    """Pick the target with hysteresis: an existing target is only dropped for one that is
    better by more than ``delta``, so recalculated scores cannot make the agent flip-flop."""
    if not ranked:
        return Choice(None, current is not None, "no eligible person")
    best = ranked[0]
    by_id = {s.person_id: s for s in ranked}
    if current is None:
        return Choice(best.person_id, False, f"{best.person_id} has the highest priority")
    if current not in by_id:
        why = f"{current} is no longer eligible; {best.person_id} has the highest priority"
        return Choice(best.person_id, True, why)
    mine = by_id[current]
    if best.person_id == current:
        return Choice(current, False, f"{current} is still the highest priority")
    margin = f"{best.person_id} ({best.score:g}) vs {current} ({mine.score:g}), δ={delta:g}"
    if best.score > mine.score + delta:
        return Choice(best.person_id, True, f"switching target: {margin} exceeds the margin")
    return Choice(current, False, f"keeping {current}: {margin} is within the margin")
