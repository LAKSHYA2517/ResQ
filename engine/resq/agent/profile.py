"""Module 1: what kind of agent this is and what kind of environment it is in.

The PEAS description is fixed text. The environment properties are *derived from the scenario's
parameters*, so they change when the mode is toggled (static fire vs spreading vs adversarial).
"""

from dataclasses import dataclass

from ..world.scenarios import Scenario

PEAS: dict[str, tuple[str, ...]] = {
    "Performance": (
        "people evacuated",
        "total path cost paid",
        "ticks taken",
        "priority-weighted completion time",
        "number of replans",
    ),
    "Environment": (
        "grid of floor, rubble and walls",
        "fire and the Hot zone around it",
        "people waiting to be rescued",
        "exits that can be blocked",
    ),
    "Actuators": ("move one cell", "pick up one person", "drop off at an exit"),
    "Sensors": (
        "full map of terrain, fire, people and exits",
        "smoke, heat and voice sensors per person (feed the Bayesian network)",
    ),
}

AGENT_TYPE = (
    "Utility-based, goal-driven agent with an internal model: it keeps a knowledge base, chooses"
    " a goal by a priority (utility) function, plans to reach it and monitors execution."
)


@dataclass(frozen=True)
class Property:
    dimension: str
    value: str
    why: str


def environment(scenario: Scenario) -> tuple[Property, ...]:
    p = scenario.params
    adversarial = p.fire_mode == "adversarial"
    spreading = p.p_spread > 0 and not adversarial
    scripted = len(scenario.scripted_events)
    noisy = p.sensor_noise > 0

    if noisy:
        observable = Property(
            "Observable",
            "Partially",
            f"the map is fully visible, but each person's danger is only seen through sensors"
            f" that are wrong {p.sensor_noise:.0%} of the time",
        )
    else:
        observable = Property(
            "Observable",
            "Fully (map), indirectly (danger)",
            "the agent sees the whole map; whether a person is trapped is inferred from sensors",
        )

    if adversarial:
        deterministic = Property(
            "Deterministic",
            "Strategic",
            "nothing is random, but the fire is an opponent choosing the worst ignition each tick",
        )
    elif spreading or noisy:
        causes = (
            [f"fire spreads with probability {p.p_spread:g} per neighbour"] if spreading else []
        )
        causes += ["sensor readings are noisy"] if noisy else []
        deterministic = Property("Deterministic", "Stochastic", " and ".join(causes) + " (seeded)")
    else:
        deterministic = Property(
            "Deterministic", "Deterministic", "p_spread = 0 and no sensor noise: actions decide all"
        )

    if adversarial or spreading or scripted:
        causes = []
        if adversarial or spreading:
            causes.append("the fire moves while the agent acts")
        if scripted:
            causes.append(f"{scripted} scripted event(s) will fire")
        dynamic = Property("Static", "Dynamic", "; ".join(causes))
    else:
        dynamic = Property(
            "Static", "Static", "nothing changes unless the agent acts or the user injects an event"
        )

    agents = (
        Property("Agents", "Multi-agent (competitive)", "agent (MIN) against the fire (MAX)")
        if adversarial
        else Property("Agents", "Single agent", "the fire is part of the environment, not a player")
    )
    return (
        observable,
        agents,
        deterministic,
        Property(
            "Episodic",
            "Sequential",
            "each move changes what is possible later (who can still be reached)",
        ),
        dynamic,
        Property(
            "Discrete", "Discrete", "grid cells, ticks and a finite set of actions and percepts"
        ),
        Property(
            "Known", "Known", "the agent knows the rules: costs, how fire blocks, how to rescue"
        ),
    )
