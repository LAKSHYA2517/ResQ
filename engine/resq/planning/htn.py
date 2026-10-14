"""Hierarchical (HTN) planning: decompose high-level tasks with methods until only primitive
actions are left.

    EvacuateAll        -> Evacuate(p) for each person, most urgent first
    Evacuate(p)        -> Goto(p), PickUp(p), ChooseExit(p), Goto(e), DropOff(p, e)
    Evacuate(p) [held] -> ChooseExit(p), Goto(e), DropOff(p, e)     (already carrying p)
    Goto(x)            -> Travel(here, x)   (nothing, if already there)
    ChooseExit(p)      -> the open exit cheapest to reach from p (by A*)

Unlike the STRIPS planners this does no search over orderings: the methods encode how a rescue
is done, so it is fast and readable but only as good as its methods.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from ..search.router import Router
from ..trace import TaskDecomposed, Trace
from ..world.grid import Cell, cell_name
from ..world.state import Exit, State, Status


@dataclass(frozen=True)
class TaskNode:
    task: str  # e.g. "Evacuate(p2)" or "Travel(c4_4, c7_8)"
    kind: str  # "compound", "primitive" or "choice"
    method: str  # the method used to decompose it ("" for a primitive)
    cost: float  # total cost of the primitives beneath it
    children: tuple["TaskNode", ...] = ()
    note: str = ""


@dataclass(frozen=True)
class HtnPlan:
    found: bool
    tree: TaskNode
    steps: tuple[str, ...]  # primitive action labels, in order (same names as the STRIPS domain)
    cost: float
    reason: str = ""


class HtnError(ValueError):
    """A task has no applicable method."""


def decompose(
    state: State, router: Router, people: Sequence[str], open_exits: Sequence[Exit]
) -> tuple[HtnPlan, Trace]:
    """Plan the evacuation of ``people`` in the given order by task decomposition."""
    costs = router.problem.cost_model
    trace: Trace = []
    here = state.agent.pos
    steps: list[str] = []

    def primitive(label: str, cost: float) -> TaskNode:
        steps.append(label)
        return TaskNode(label, "primitive", "", cost)

    def goto(target: Cell, what: str) -> TaskNode:
        nonlocal here
        task = f"Goto({what})"
        if here == target:
            return TaskNode(task, "compound", "already there", 0.0)
        route = router.route(here, target)
        if route.cost is None:
            raise HtnError(f"{task}: no route from {here} to {target}")
        node = primitive(f"Travel({cell_name(here)}, {cell_name(target)})", route.cost)
        here = target
        trace.append(TaskDecomposed(task, "travel", (node.task,)))
        return TaskNode(task, "compound", "travel", node.cost, (node,))

    def choose_exit(pid: str, origin: Cell) -> tuple[TaskNode, Exit]:
        options = [
            (c, e.id, e) for e in open_exits if (c := router.route(origin, e.pos).cost) is not None
        ]
        if not options:
            raise HtnError(f"ChooseExit({pid}): no open exit can be reached from {origin}")
        best = min(options, key=lambda o: (o[0], o[1]))[2]
        note = ", ".join(f"{eid}: {c:g}" for c, eid, _ in sorted(options, key=lambda o: o[:2]))
        node = TaskNode(f"ChooseExit({pid})", "choice", f"nearest -> {best.id}", 0.0, (), note)
        return node, best

    def evacuate(pid: str) -> TaskNode:
        person = state.person(pid)
        task = f"Evacuate({pid})"
        if person.status is Status.EVACUATED:
            return TaskNode(task, "compound", "already evacuated", 0.0)
        kids: list[TaskNode] = []
        if state.agent.carrying == pid and not steps:
            method = "carrying: choose exit, go, drop off"
            origin = here
        elif person.status is Status.WAITING:
            method = "go, pick up, choose exit, go, drop off"
            kids.append(goto(person.pos, pid))
            kids.append(primitive(f"PickUp({pid})", costs.pickup))
            origin = person.pos
        else:
            raise HtnError(f"{task}: {pid} is {person.status.value}, no method applies")
        choice, exit_ = choose_exit(pid, origin)
        kids += [choice, goto(exit_.pos, exit_.id)]
        kids.append(primitive(f"DropOff({pid}, {exit_.id})", costs.dropoff))
        trace.append(TaskDecomposed(task, method, tuple(k.task for k in kids)))
        return TaskNode(task, "compound", method, sum(k.cost for k in kids), tuple(kids))

    try:
        kids = tuple(evacuate(pid) for pid in people)
    except HtnError as err:
        root = TaskNode("EvacuateAll", "compound", "failed", 0.0, (), str(err))
        return HtnPlan(False, root, (), 0.0, str(err)), trace
    root = TaskNode(
        "EvacuateAll", "compound", "one Evacuate per person, in priority order",
        sum(k.cost for k in kids), kids,
    )  # fmt: skip
    trace.append(TaskDecomposed(root.task, root.method, tuple(k.task for k in kids)))
    return HtnPlan(True, root, tuple(steps), root.cost), trace
