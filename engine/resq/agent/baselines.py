"""Three kinds of agent on identical scenarios (AIMA chapter 2), for the Module 1 benchmark.

* **simple reflex**: condition-action rules on the current percept only. No map, no memory, no
  search: it walks towards the nearest person (or exit) as the crow flies and takes the first
  open step that gets closer. Walls and fire in the way defeat it.
* **goal-based**: has the map and searches. A* to the nearest reachable person, then A* to the
  nearest exit, recomputed every tick. It has a goal but no preferences among goals.
* **utility-based**: the full ResQ agent: knowledge base, Bayes risk, priority (utility)
  function, STRIPS plan, execution monitoring.

All three face the same world: same fire spread (same seed), same scripted events, same costs.
"""

from collections.abc import Callable
from dataclasses import dataclass

from ..search.router import Router
from ..world.grid import Cell, moves
from ..world.scenarios import Scenario
from ..world.session import apply_events, spread_tick, start
from ..world.state import State, Status
from .agent import ActionError, drop_off, enter_cost, move, pick_up
from .loop import Simulation

AGENT_KINDS = ("reflex", "goal", "utility")
# ("move", cell) | ("pick", person id) | ("drop", exit id) | ("wait", None), plus the cell aimed for
type Step = tuple[str, Cell | str | None, Cell | None]


@dataclass(frozen=True)
class BenchRow:
    agent: str
    scenario: str
    rescued: int
    people: int
    cost: float
    ticks: int
    replans: int  # utility: plans dropped or replaced; others: changes of destination mid-walk
    finished: bool  # False: stopped by the tick limit (e.g. a reflex agent pacing in a dead end)


def _manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _usable_exits(state: State) -> list[tuple[str, Cell]]:
    return [(e.id, e.pos) for e in state.exits if e.available and e.pos not in state.fire]


def reflex_policy(state: State, scenario: Scenario) -> Step:
    """Percept -> action. Looks only at its own cell, its four neighbours and a compass."""
    here = state.agent.pos
    carrying = state.agent.carrying
    if carrying is not None:
        for exit_id, pos in _usable_exits(state):
            if pos == here:
                return ("drop", exit_id, here)
        targets = [pos for _, pos in _usable_exits(state)]
    else:
        waiting = [p for p in state.people if p.status is Status.WAITING]
        for p in waiting:
            if p.pos == here:
                return ("pick", p.id, here)
        targets = [p.pos for p in waiting]
    if not targets:
        return ("wait", None, None)
    goal = min(targets, key=lambda c: (_manhattan(here, c), c))
    for _, n in moves(here, state.rows, state.cols):
        if not state.is_blocked(n) and _manhattan(n, goal) < _manhattan(here, goal):
            return ("move", n, goal)
    return ("wait", None, goal)  # every closer cell is blocked: a reflex agent has no way round


def goal_policy(state: State, scenario: Scenario) -> Step:
    """A* to the nearest reachable person, then to the nearest reachable exit."""
    here = state.agent.pos
    router = Router(state, scenario.params.cost_model)
    if state.agent.carrying is not None:
        targets = {pos: ("drop", eid) for eid, pos in _usable_exits(state)}
    else:
        targets = {p.pos: ("pick", p.id) for p in state.people if p.status is Status.WAITING}
    if here in targets:
        return (*targets[here], here)
    routes = [r for c in sorted(targets) if (r := router.route(here, c)).found]
    if not routes:
        return ("wait", None, None)
    best = min(routes, key=lambda r: (r.cost or 0.0, r.path[-1]))
    return ("move", best.path[1], best.path[-1])


def _run_policy(
    kind: str, policy: Callable[[State, Scenario], Step], scenario: Scenario, max_ticks: int
) -> BenchRow:
    state, _ = start(scenario)
    cost = 0.0
    replans = 0
    aim: Cell | None = None
    idle = 0
    costs = scenario.params.cost_model
    last_event = max((e.tick for e in scenario.scripted_events), default=0)
    while state.tick < max_ticks:
        active = [p for p in state.people if p.status in (Status.WAITING, Status.CARRIED)]
        if not active:
            break
        action, arg, target = policy(state, scenario)
        if action == "move" and aim is not None and target != aim:
            replans += 1  # it changed its mind about where it is going
        aim = target if action == "move" else None
        try:
            if action == "move" and isinstance(arg, tuple):
                cost += enter_cost(state, arg, costs)
                state = move(state, arg)
            elif action == "pick" and isinstance(arg, str):
                state, cost = pick_up(state, arg), cost + costs.pickup
            elif action == "drop" and isinstance(arg, str) and state.agent.carrying:
                state = drop_off(state, state.agent.carrying, arg)
                cost += costs.dropoff
        except ActionError:
            action = "wait"
        idle = idle + 1 if action == "wait" else 0
        state, _ = spread_tick(scenario, state)
        state, _ = apply_events(
            state, tuple(e for e in scenario.scripted_events if e.tick == state.tick)
        )
        if idle >= 3 and state.tick > last_event and scenario.params.p_spread == 0:
            break  # nothing will ever change: the agent is stuck for good
        if idle >= 12 and state.tick > last_event:
            break  # waited long enough for a spreading fire to open nothing
    rescued = sum(p.status is Status.EVACUATED for p in state.people)
    done = all(p.status in (Status.EVACUATED, Status.TRAPPED) for p in state.people)
    return BenchRow(
        kind, scenario.name, rescued, len(state.people), cost, state.tick, replans,
        done or state.tick < max_ticks,
    )  # fmt: skip


def run_agent(kind: str, scenario: Scenario, max_ticks: int = 400) -> BenchRow:
    """Run one kind of agent on one scenario to the end and measure it."""
    if kind == "reflex":
        return _run_policy(kind, reflex_policy, scenario, max_ticks)
    if kind == "goal":
        return _run_policy(kind, goal_policy, scenario, max_ticks)
    if kind == "utility":
        end = Simulation(scenario).run(max_ticks)
        m = end.metrics
        return BenchRow(
            kind, scenario.name, m.rescued, len(scenario.people), m.path_cost, end.tick,
            m.replans, end.finished,
        )  # fmt: skip
    raise ValueError(f"unknown agent kind {kind!r}; choose from {AGENT_KINDS}")


@dataclass(frozen=True)
class BenchSummary:
    agent: str
    scenarios: int
    rescued: int
    people: int
    rescued_pct: float
    mean_cost: float
    mean_ticks: float
    cost_per_rescue: float | None
    replans: int


def benchmark(scenarios: list[Scenario]) -> tuple[list[BenchRow], list[BenchSummary]]:
    rows = [run_agent(kind, s) for s in scenarios for kind in AGENT_KINDS]
    summaries = []
    for kind in AGENT_KINDS:
        mine = [r for r in rows if r.agent == kind]
        rescued, people = sum(r.rescued for r in mine), sum(r.people for r in mine)
        cost = sum(r.cost for r in mine)
        summaries.append(
            BenchSummary(
                agent=kind,
                scenarios=len(mine),
                rescued=rescued,
                people=people,
                rescued_pct=100 * rescued / people if people else 0.0,
                mean_cost=cost / len(mine) if mine else 0.0,
                mean_ticks=sum(r.ticks for r in mine) / len(mine) if mine else 0.0,
                cost_per_rescue=cost / rescued if rescued else None,
                replans=sum(r.replans for r in mine),
            )
        )
    return rows, summaries
