from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from resq.agent.loop import Snapshot
from resq.search import compare
from resq.search.heuristics import check_heuristic, make_heuristic
from resq.search.problem import GridProblem
from resq.world.state import Status

from ..schemas import Cell, ErrorOut
from ..sessions import Session, snapshot_at

router = APIRouter(prefix="/search", tags=["search"], responses={404: {"model": ErrorOut}})

AlgorithmName = Literal["bfs", "dfs", "dls", "iddfs", "ucs", "greedy", "astar", "weighted_astar"]
HeuristicName = Literal["manhattan", "euclidean", "zero", "weighted"]


class RunSpec(BaseModel):
    algorithm: AlgorithmName
    heuristic: HeuristicName | None = None  # informed algorithms default to manhattan


class CompareIn(BaseModel):
    session_id: str
    tick: int | None = None  # default: the live tick
    target: str | None = None  # person id; default: the agent's target, else the first waiting
    runs: list[RunSpec] = [
        RunSpec(algorithm="bfs"),
        RunSpec(algorithm="ucs"),
        RunSpec(algorithm="astar", heuristic="manhattan"),
    ]
    limit: int = Field(20, ge=0, le=2000)  # depth limit for DLS
    w: float = Field(2.0, ge=0, le=50)  # weight for weighted A* and the weighted heuristic


class SearchRunOut(BaseModel):
    label: str
    algorithm: str
    heuristic: str | None
    found: bool
    cost: float | None
    steps: int
    expanded: int
    generated: int
    max_frontier: int
    time_ms: float
    optimal_vs_ucs: bool | None  # computed against a reference UCS run
    reason: str
    depth_limit: int | None
    path: list[Cell]
    expansion_order: list[Cell]


class CompareOut(BaseModel):
    tick: int
    source: Cell
    target_id: str
    goal: Cell
    runs: list[SearchRunOut]


def grid_problem(session: Session, snap: Snapshot, target: str | None) -> tuple[GridProblem, str]:
    """Agent -> a waiting person at this snapshot (409 if there is nobody to search for)."""
    state = snap.state
    waiting = [p for p in state.people if p.status is Status.WAITING]
    wanted = target or snap.target or (waiting[0].id if waiting else None)
    person = next((p for p in waiting if p.id == wanted), None)
    if person is None:
        raise HTTPException(409, f"no waiting person {wanted!r} to search for at tick {snap.tick}")
    costs = session.sim.scenario.params.cost_model
    return GridProblem(state, state.agent.pos, {person.pos}, costs), person.id


@router.post("/compare", responses={409: {"model": ErrorOut}})
async def search_compare(body: CompareIn) -> CompareOut:
    """Run algorithms x heuristics on the same problem (agent -> person at the chosen tick)."""
    session, snap = snapshot_at(body.session_id, body.tick)
    problem, person_id = grid_problem(session, snap, body.target)
    specs = [(r.algorithm, r.heuristic) for r in body.runs]
    runs = [
        SearchRunOut(
            label=r.label,
            algorithm=r.algorithm,
            heuristic=r.heuristic,
            found=r.result.found,
            cost=r.result.cost,
            steps=len(r.result.actions),
            expanded=r.result.expanded,
            generated=r.result.generated,
            max_frontier=r.result.max_frontier,
            time_ms=r.result.time_ms,
            optimal_vs_ucs=r.result.optimal_vs_ucs,
            reason=r.result.reason,
            depth_limit=r.result.depth_limit,
            path=list(r.result.path),
            expansion_order=list(r.result.expansion_order),
        )
        for r in compare(problem, specs, body.limit, body.w)
    ]
    goal = next(iter(problem.goals))
    return CompareOut(
        tick=snap.tick, source=problem.initial, target_id=person_id, goal=goal, runs=runs
    )


class HeuristicIn(BaseModel):
    session_id: str
    tick: int | None = None
    target: str | None = None
    heuristic: HeuristicName = "manhattan"
    w: float = Field(2.0, ge=0, le=50)


class AdmissibilityViolation(BaseModel):
    cell: Cell
    h: float
    true_cost: float


class ConsistencyViolation(BaseModel):
    cell: Cell
    next_cell: Cell
    h: float
    step_cost: float
    h_next: float


class HeuristicOut(BaseModel):
    heuristic: str
    w: float
    target_id: str
    goal: Cell
    admissible: bool
    consistent: bool
    n_admissibility_violations: int
    n_consistency_violations: int
    admissibility_violations: list[AdmissibilityViolation]  # first few only
    consistency_violations: list[ConsistencyViolation]
    astar: SearchRunOut  # A* using this heuristic, with optimality computed against UCS


@router.post("/heuristic-check", responses={409: {"model": ErrorOut}})
async def heuristic_check(body: HeuristicIn) -> HeuristicOut:
    """Check h(n) <= h*(n) and h(n) <= c(n, n') + h(n') over every passable cell, exhaustively."""
    session, snap = snapshot_at(body.session_id, body.tick)
    problem, person_id = grid_problem(session, snap, body.target)
    check = check_heuristic(problem, make_heuristic(body.heuristic, problem, body.w))
    run = compare(problem, [("astar", body.heuristic)], w=body.w)[0]
    r = run.result
    return HeuristicOut(
        heuristic=body.heuristic,
        w=body.w,
        target_id=person_id,
        goal=next(iter(problem.goals)),
        admissible=check.admissible,
        consistent=check.consistent,
        n_admissibility_violations=check.n_admissibility_violations,
        n_consistency_violations=check.n_consistency_violations,
        admissibility_violations=[
            AdmissibilityViolation(cell=c, h=h, true_cost=t)
            for c, h, t in check.admissibility_violations
        ],
        consistency_violations=[
            ConsistencyViolation(cell=c, next_cell=n, h=h, step_cost=sc, h_next=hn)
            for c, n, h, sc, hn in check.consistency_violations
        ],
        astar=SearchRunOut(
            label=run.label,
            algorithm=run.algorithm,
            heuristic=run.heuristic,
            found=r.found,
            cost=r.cost,
            steps=len(r.actions),
            expanded=r.expanded,
            generated=r.generated,
            max_frontier=r.max_frontier,
            time_ms=r.time_ms,
            optimal_vs_ucs=r.optimal_vs_ucs,
            reason=r.reason,
            depth_limit=r.depth_limit,
            path=list(r.path),
            expansion_order=list(r.expansion_order),
        ),
    )
