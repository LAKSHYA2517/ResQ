"""Forward (progression) planner: A* over STRIPS states, reusing the search core."""

from collections.abc import Iterator

from ..search.informed import best_first
from ..search.problem import Heuristic
from ..trace import NodeExpanded, PlanFailed, PlanFound, PlanStateExpanded, Trace
from .strips import Plan, PlanState, StripsProblem


class _StateSpace:
    """Adapts a STRIPS problem to the search ``Problem`` interface."""

    def __init__(self, problem: StripsProblem) -> None:
        self.problem = problem
        self.initial: PlanState = problem.initial

    def is_goal(self, state: PlanState) -> bool:
        return self.problem.goal <= state

    def successors(self, state: PlanState) -> Iterator[tuple[str, PlanState, float]]:
        for action in self.problem.actions:
            if action.applicable(state):
                yield action.label, action.apply(state), action.cost


def plan(
    problem: StripsProblem, heuristic: Heuristic[PlanState] | None = None
) -> tuple[Plan, Trace]:
    """Cheapest plan from ``problem.initial`` to a state containing the goal.

    With an admissible ``heuristic`` this is A* and the plan is optimal; with ``None`` it is
    uniform-cost search over states (also optimal, more states expanded).
    """
    result, search_trace = best_first(_StateSpace(problem), "forward", heuristic, snapshots=0)
    expansions = [e for e in search_trace if isinstance(e, NodeExpanded)]
    trace: Trace = [
        PlanStateExpanded(tuple(sorted(map(str, state))), e.g, e.h, e.f, e.frontier_size)
        for state, e in zip(result.expansion_order, expansions, strict=True)
    ]
    by_label = {a.label: a for a in problem.actions}
    steps = tuple(by_label[label] for label in result.actions)
    reason = ""
    if result.cost is None:
        missing = sorted(str(g) for g in problem.goal - problem.initial)
        reason = f"no action sequence achieves {', '.join(missing)}"
        trace.append(PlanFailed(reason, result.expanded))
    else:
        trace.append(PlanFound(result.actions, result.cost, result.expanded))
    return (
        Plan(
            found=result.found,
            steps=steps,
            cost=result.cost,
            expanded=result.expanded,
            generated=result.generated,
            max_frontier=result.max_frontier,
            reason=reason,
            time_ms=result.time_ms,
        ),
        trace,
    )
