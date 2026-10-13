"""The abstract rescue domain, grounded for one world state.

Predicates: ``At(l)``, ``Carrying(p)``, ``HandsFree``, ``Waiting(p)``, ``Evacuated(p)``,
``ExitOpen(e)``. Actions: ``Travel(a, b)`` (cost and concrete path from A*), ``PickUp(p)``,
``DropOff(p, e)``. Locations are cells, named like the KB's cell constants.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..logic.terms import Atom, atom
from ..search.router import Router
from ..world.grid import Cell, cell_name
from ..world.state import Exit, State, Status
from .strips import Action, Plan, PlanState, StripsProblem

HANDS_FREE = atom("HandsFree")


def at(cell: Cell) -> Atom:
    return atom("At", cell_name(cell))


@dataclass(frozen=True)
class PlanStep:
    """An abstract action plus, for Travel, the concrete cells ``a .. b`` that realise it."""

    action: Action
    route: tuple[Cell, ...] = ()


@dataclass(frozen=True)
class RescueDomain:
    problem: StripsProblem
    heuristic: Callable[[PlanState], float]
    routes: dict[str, tuple[Cell, ...]]  # Travel label -> A* path
    notes: tuple[str, ...]  # options that could not be grounded, and why

    def steps(self, plan: Plan) -> tuple[PlanStep, ...]:
        return tuple(PlanStep(a, self.routes.get(a.label, ())) for a in plan.steps)


def live_atoms(state: State, open_exits: Sequence[Exit]) -> set[Atom]:
    """The world as STRIPS atoms, except ``At`` (the caller knows where the agent is)."""
    atoms = {atom("Waiting", p.id) for p in state.people if p.status is Status.WAITING}
    atoms |= {atom("ExitOpen", e.id) for e in open_exits}
    atoms |= {atom("Evacuated", p.id) for p in state.people if p.status is Status.EVACUATED}
    carrying = state.agent.carrying
    atoms.add(HANDS_FREE if carrying is None else atom("Carrying", carrying))
    return atoms


def build_domain(
    state: State, router: Router, goal_people: Sequence[str], open_exits: Sequence[Exit]
) -> RescueDomain:
    """Ground the domain for evacuating ``goal_people`` from the current state.

    Travel is only grounded where it can be useful under capacity one: from the agent's cell
    to a person (or to an exit if already carrying), from a person to an exit, and from an exit
    to another person. Shortest-path costs obey the triangle inequality, so detouring through a
    waypoint without acting there never helps and leaving those edges out loses no optimal plan.
    """
    costs = router.problem.cost_model
    here = state.agent.pos
    carrying = state.agent.carrying
    waiting = [state.person(p) for p in goal_people if state.person(p).status is Status.WAITING]
    travel: dict[tuple[Cell, Cell], float] = {}
    actions: dict[str, Action] = {}
    routes: dict[str, tuple[Cell, ...]] = {}
    notes: list[str] = []

    def add_travel(src: Cell, dst: Cell, what: str) -> None:
        if src == dst or (src, dst) in travel:
            return
        result = router.route(src, dst)
        if result.cost is None:
            notes.append(f"no route from {src} to {what} at {dst}")
            return
        travel[(src, dst)] = result.cost
        action = Action(
            "Travel",
            (cell_name(src), cell_name(dst)),
            frozenset({at(src)}),
            frozenset({at(dst)}),
            frozenset({at(src)}),
            result.cost,
        )
        actions[action.label] = action
        routes[action.label] = result.path

    if not open_exits:
        notes.append("no exit is open")
    for p in waiting:
        add_travel(here, p.pos, f"person {p.id}")
        pick = Action(
            "PickUp",
            (p.id,),
            frozenset({at(p.pos), atom("Waiting", p.id), HANDS_FREE}),
            frozenset({atom("Carrying", p.id)}),
            frozenset({atom("Waiting", p.id), HANDS_FREE}),
            costs.pickup,
        )
        actions[pick.label] = pick
    for e in open_exits:
        if carrying is not None:
            add_travel(here, e.pos, f"exit {e.id}")
        for p in waiting:
            add_travel(p.pos, e.pos, f"exit {e.id}")
            if len(waiting) + (carrying is not None) > 1:
                add_travel(e.pos, p.pos, f"person {p.id}")
        for pid in goal_people:
            drop = Action(
                "DropOff",
                (pid, e.id),
                frozenset({at(e.pos), atom("Carrying", pid), atom("ExitOpen", e.id)}),
                frozenset({atom("Evacuated", pid), HANDS_FREE}),
                frozenset({atom("Carrying", pid)}),
                costs.dropoff,
            )
            actions[drop.label] = drop

    exit_cells = [e.pos for e in open_exits]
    person_cell = {p.id: p.pos for p in waiting}

    def to_nearest_exit(src: Cell) -> float:
        legs = (0.0 if src == e else travel.get((src, e), math.inf) for e in exit_cells)
        return min(legs, default=math.inf)

    carry_cost = {pid: to_nearest_exit(cell) for pid, cell in person_cell.items()}
    waypoints = {here, *exit_cells, *person_cell.values()}
    from_cell = {cell_name(c): to_nearest_exit(c) for c in waypoints}

    def heuristic(s: PlanState) -> float:
        """Admissible: every unrescued person must still be carried, alone, from where they
        are to some exit and dropped there; travel to reach them is ignored."""
        where = next(str(a.args[0]) for a in s if a.pred == "At")
        total = 0.0
        for pid in goal_people:
            if atom("Evacuated", pid) in s:
                continue
            if atom("Carrying", pid) in s:
                total += from_cell[where] + costs.dropoff
            else:
                total += costs.pickup + carry_cost.get(pid, math.inf) + costs.dropoff
        return total

    initial = frozenset(live_atoms(state, open_exits) | {at(here)})
    goal = frozenset(atom("Evacuated", pid) for pid in goal_people)
    problem = StripsProblem(initial, goal, tuple(actions[k] for k in sorted(actions)))
    return RescueDomain(problem, heuristic, routes, tuple(notes))
