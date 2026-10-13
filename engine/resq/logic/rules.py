"""The rescue domain: core rules, and the translation of a world state into base facts."""

from collections.abc import Collection
from functools import lru_cache

from ..world.grid import cell_name, moves
from ..world.state import State, Status
from ..world.terrain import Terrain
from .terms import Atom, atom, parse_rules

# At-risk is not the same as must-rescue-first: RescueNow is only a candidate flag, the actual
# ordering is the priority score in decision/priority.py.
CORE_RULES = parse_rules(
    """
    fire_unsafe:   Fire(X) -> Unsafe(X)
    hot_zone:      Adjacent(X, Y) & Fire(Y) -> Hot(X)
    hot_unsafe:    Hot(X) -> Unsafe(X)
    at_risk:       Person(P, X) & Unsafe(X) -> AtRisk(P)
    trapped:       Person(P, X) & Fire(X) -> Trapped(P)
    exit_on_fire:  Exit(E, X) & Fire(X) -> Unavailable(E)
    exit_blocked:  Exit(E, X) & Blocked(X) -> Unavailable(E)
    eligible:      Waiting(P) & Reachable(P) -> Eligible(P)
    critical:      AtRisk(P) & Urgent(P) -> Critical(P)
    rescue_now:    Eligible(P) & Critical(P) -> RescueNow(P)
    """
)

# Static grid geometry: by far the most numerous facts, and never interesting to read.
GEOMETRY_PREDICATES = frozenset({"Adjacent"})


@lru_cache(maxsize=16)
def _adjacency(terrain: tuple[tuple[Terrain, ...], ...]) -> tuple[Atom, ...]:
    """Adjacent(X, Y) for every ordered pair of 4-neighbouring non-wall cells. Cached per
    terrain, so the atoms are shared between ticks until an obstacle event changes the grid."""
    rows, cols = len(terrain), len(terrain[0])
    out = []
    for r in range(rows):
        for c in range(cols):
            if terrain[r][c] is Terrain.WALL:
                continue
            for _, (nr, nc) in moves((r, c), rows, cols):
                if terrain[nr][nc] is not Terrain.WALL:
                    out.append(atom("Adjacent", cell_name((r, c)), cell_name((nr, nc))))
    return tuple(out)


def base_facts(
    state: State, reachable: Collection[str], urgent: Collection[str]
) -> tuple[Atom, ...]:
    """Everything the agent knows directly, rebuilt from scratch from the state.

    ``reachable`` (person ids with an A* route from the agent) and ``urgent`` (ids whose
    time-grown urgency passed the threshold) are computed outside the logic, because Horn
    clauses over symbols cannot do search or arithmetic; they enter the KB as plain facts.
    """
    facts = [atom("AgentAt", cell_name(state.agent.pos))]
    if state.agent.carrying is not None:
        facts.append(atom("Carrying", state.agent.carrying))
    for p in state.people:
        if p.status is Status.EVACUATED:
            facts.append(atom("Evacuated", p.id))
            continue
        facts.append(atom("Person", p.id, cell_name(p.pos)))
        if p.status is Status.WAITING:
            facts.append(atom("Waiting", p.id))
        if p.id in reachable:
            facts.append(atom("Reachable", p.id))
        if p.id in urgent:
            facts.append(atom("Urgent", p.id))
    for e in state.exits:
        facts.append(atom("Exit", e.id, cell_name(e.pos)))
        if not e.available:
            facts.append(atom("Blocked", cell_name(e.pos)))
    facts.extend(atom("Fire", cell_name(c)) for c in sorted(state.fire))
    facts.extend(_adjacency(state.terrain))
    return tuple(facts)
