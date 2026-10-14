"""Backward (regression) planner: search from the goal back to the initial state.

A search node is a *set of sub-goals*. Regressing through an action replaces the sub-goals it
achieves by its preconditions:

    relevant(a, g):   a.add intersects g   and   a.delete does not intersect g
    regress(g, a)  =  (g - a.add) | a.pre

The search stops at a goal set that already holds in the initial state. Uniform-cost search over
goal sets returns a cheapest plan, so its cost must equal the forward planner's.
"""

from collections.abc import Callable, Iterator

from ..logic.terms import Atom
from ..search.informed import best_first
from ..trace import NodeExpanded, PlanFailed, PlanFound, PlanStateExpanded, Trace
from .strips import Plan, PlanState, StripsProblem


class _GoalSpace:
    def __init__(
        self, problem: StripsProblem, consistent: Callable[[PlanState], bool] | None
    ) -> None:
        self.problem = problem
        self.initial: PlanState = problem.goal
        self.consistent = consistent

    def is_goal(self, goals: PlanState) -> bool:
        return goals <= self.problem.initial

    def successors(self, goals: PlanState) -> Iterator[tuple[str, PlanState, float]]:
        for action in self.problem.actions:
            if action.add & goals and not action.delete & goals:
                regressed = (goals - action.add) | action.pre
                if self.consistent is None or self.consistent(regressed):
                    yield action.label, regressed, action.cost


def one_place_one_load(goals: frozenset[Atom]) -> bool:
    """Domain knowledge for the rescue domain: no state has the agent in two places, carrying
    two people, or carrying someone with free hands. Sub-goal sets that demand such a state can
    never be satisfied, so regression may drop them (it prunes, it never changes the answer)."""
    at = sum(a.pred == "At" for a in goals)
    carrying = sum(a.pred == "Carrying" for a in goals)
    hands_free = any(a.pred == "HandsFree" for a in goals)
    return at <= 1 and carrying <= 1 and not (carrying and hands_free)


def plan_backward(
    problem: StripsProblem, consistent: Callable[[PlanState], bool] | None = None
) -> tuple[Plan, Trace]:
    """Cheapest plan by regression. ``consistent`` optionally prunes impossible sub-goal sets."""
    space = _GoalSpace(problem, consistent)
    result, search_trace = best_first(space, "regression", None, snapshots=0)
    expansions = [e for e in search_trace if isinstance(e, NodeExpanded)]
    trace: Trace = [
        PlanStateExpanded(tuple(sorted(map(str, goals))), e.g, e.h, e.f, e.frontier_size)
        for goals, e in zip(result.expansion_order, expansions, strict=True)
    ]
    by_label = {a.label: a for a in problem.actions}
    # the search walked goal -> start, so the actions come out last-first
    steps = tuple(by_label[label] for label in reversed(result.actions))
    reason = ""
    if result.cost is None:
        missing = sorted(str(g) for g in problem.goal - problem.initial)
        reason = f"no action sequence achieves {', '.join(missing)}"
        trace.append(PlanFailed(reason, result.expanded))
    else:
        trace.append(PlanFound(tuple(a.label for a in steps), result.cost, result.expanded))
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
