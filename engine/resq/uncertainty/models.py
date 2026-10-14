"""The sensor model for one person's zone, and how its posterior becomes ``Risk(P)``.

    Fire -> Smoke        Fire -> Heat        Fire -> Trapped -> Voice

Fire and Trapped are hidden. Smoke, Heat and Voice are simulated sensor readings taken from
the true world state (optionally corrupted by noise). The numbers are simulation values chosen
so that both the prior and the evidence visibly matter; they are not calibrated to real fires.
"""

from dataclasses import dataclass
from random import Random

from ..world.state import Person, State
from .bayesnet import BayesNet, Node
from .exact import elimination

SENSORS = ("Smoke", "Heat", "Voice")
SMOKE_RANGE = 2  # smoke is sensed up to this Manhattan distance from a fire cell


def prior_from_risk(risk: int) -> float:
    """A scenario's baseline risk (0..5) is the prior belief that the zone is on fire."""
    return min(0.95, max(0.05, risk / 5))


def sensor_network(p_fire: float = 0.2) -> BayesNet:
    return BayesNet(
        [
            Node("Fire", (), {(): p_fire}),
            Node("Smoke", ("Fire",), {(True,): 0.7, (False,): 0.3}),
            Node("Heat", ("Fire",), {(True,): 0.6, (False,): 0.2}),
            Node("Trapped", ("Fire",), {(True,): 0.8, (False,): 0.05}),
            Node("Voice", ("Trapped",), {(True,): 0.6, (False,): 0.2}),
        ]
    )


def read_sensors(state: State, person: Person, seed: int, noise: float) -> dict[str, bool]:
    """Simulated readings for the person's zone at this tick.

    Truth: smoke if a fire is within ``SMOKE_RANGE`` cells; heat and a call for help if the
    person's cell is burning or in the Hot zone. Each reading is flipped with probability
    ``noise``, using an RNG derived from (seed, tick, person, sensor) so replay is exact.
    """
    r, c = person.pos
    near = min((abs(r - fr) + abs(c - fc) for fr, fc in state.fire), default=99)
    unsafe = person.pos in state.fire or person.pos in state.hot
    truth = {"Smoke": near <= SMOKE_RANGE, "Heat": unsafe, "Voice": unsafe}
    if noise <= 0:
        return truth
    return {
        name: value != (Random(f"{seed}:{state.tick}:{person.id}:{name}").random() < noise)
        for name, value in truth.items()
    }


def risk_from_posterior(p_trapped: float) -> int:
    """Risk(P) = round(5 * P(Trapped | evidence)), with halves rounding up."""
    return int(5 * p_trapped + 0.5)


@dataclass(frozen=True)
class Belief:
    person_id: str
    prior_fire: float
    evidence: tuple[tuple[str, bool], ...]
    p_fire: float
    p_trapped: float
    risk: int


def assess(state: State, person: Person, seed: int, noise: float) -> Belief:
    """Exact posterior for one person from this tick's sensor readings."""
    prior = prior_from_risk(person.risk)
    bn = sensor_network(prior)
    evidence = read_sensors(state, person, seed, noise)
    p_fire = elimination(bn, "Fire", evidence)[0].p_true
    p_trapped = elimination(bn, "Trapped", evidence)[0].p_true
    return Belief(
        person.id,
        prior,
        tuple(evidence.items()),
        p_fire,
        p_trapped,
        risk_from_posterior(p_trapped),
    )
