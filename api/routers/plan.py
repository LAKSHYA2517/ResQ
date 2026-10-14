from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from resq.logic.terms import atom
from resq.planning.domain import build_domain
from resq.planning.fwd_planner import plan
from resq.planning.regression import one_place_one_load, plan_backward
from resq.planning.strips import Plan
from resq.search.router import Router
from resq.world.state import Status

from ..schemas import ErrorOut
from ..sessions import snapshot_at

router = APIRouter(prefix="/plan", tags=["plan"], responses={404: {"model": ErrorOut}})

MAX_PEOPLE = 4  # joint plans grow quickly; beyond this the comparison would take too long


class PlanCompareIn(BaseModel):
    session_id: str
    tick: int | None = None
    scope: Literal["target", "all"] = "target"  # plan for the current target, or for everyone


class PlannerRow(BaseModel):
    planner: str
    found: bool
    cost: float | None
    steps: list[str]
    expanded: int
    generated: int
    max_frontier: int
    time_ms: float
    reason: str


class PlanCompareOut(BaseModel):
    tick: int
    goal: list[str]  # the STRIPS goal atoms
    people: list[str]
    note: str
    actions: int  # ground actions in the problem
    rows: list[PlannerRow]
    equal_cost: bool  # every planner that found a plan found one of the same cost


def _row(name: str, p: Plan) -> PlannerRow:
    return PlannerRow(
        planner=name,
        found=p.found,
        cost=p.cost,
        steps=[a.label for a in p.steps],
        expanded=p.expanded,
        generated=p.generated,
        max_frontier=p.max_frontier,
        time_ms=p.time_ms,
        reason=p.reason,
    )


@router.post("/compare", responses={409: {"model": ErrorOut}})
async def plan_compare(body: PlanCompareIn) -> PlanCompareOut:
    """Forward (progression) vs backward (regression) planning on the same STRIPS problem."""
    session, snap = snapshot_at(body.session_id, body.tick)
    state = snap.state
    carrying = state.agent.carrying
    ranked = [p.person_id for p in snap.priorities]
    note = ""
    if body.scope == "all":
        people = ([carrying] if carrying else []) + ranked
        if len(people) > MAX_PEOPLE:
            note = (
                f"planning for the {MAX_PEOPLE} highest-priority people of {len(people)}"
                " (a joint plan for everyone would take too long to compare)"
            )
            people = people[:MAX_PEOPLE]
    else:
        people = [snap.target] if snap.target else []
    if not people:
        raise HTTPException(409, f"nobody to plan for at tick {snap.tick}")
    waiting_or_carried = {
        p.id for p in state.people if p.status in (Status.WAITING, Status.CARRIED)
    }
    people = [p for p in people if p in waiting_or_carried]
    unavailable = {d.fact for d in snap.derived if d.fact.pred == "Unavailable"}
    open_exits = [e for e in state.exits if atom("Unavailable", e.id) not in unavailable]
    router_ = Router(state, session.sim.scenario.params.cost_model)
    domain = build_domain(state, router_, people, open_exits)
    plans = [
        ("forward A* (admissible h)", plan(domain.problem, domain.heuristic)[0]),
        ("forward uniform-cost", plan(domain.problem)[0]),
        ("regression + domain pruning", plan_backward(domain.problem, one_place_one_load)[0]),
        ("regression (plain)", plan_backward(domain.problem)[0]),
    ]
    costs = {round(p.cost, 9) for _, p in plans if p.cost is not None}
    return PlanCompareOut(
        tick=snap.tick,
        goal=sorted(str(g) for g in domain.problem.goal),
        people=people,
        note=note,
        actions=len(domain.problem.actions),
        rows=[_row(name, p) for name, p in plans],
        equal_cost=len(costs) <= 1 and len({p.found for _, p in plans}) == 1,
    )
