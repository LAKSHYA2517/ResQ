from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from resq.search import compare
from resq.search.problem import GridProblem
from resq.world.state import Status

from ..schemas import Cell, ErrorOut
from ..sessions import store

router = APIRouter(prefix="/search", tags=["search"], responses={404: {"model": ErrorOut}})

AlgorithmName = Literal["bfs", "ucs", "astar"]  # P4 adds dfs, dls, iddfs, greedy, weighted_astar
HeuristicName = Literal["manhattan", "euclidean", "zero", "weighted"]


class RunSpec(BaseModel):
    algorithm: AlgorithmName
    heuristic: HeuristicName | None = None  # A* defaults to manhattan; others ignore it


class CompareIn(BaseModel):
    session_id: str
    tick: int | None = None  # default: the live tick
    target: str | None = None  # person id; default: the agent's target, else the first waiting
    runs: list[RunSpec] = [
        RunSpec(algorithm="bfs"),
        RunSpec(algorithm="ucs"),
        RunSpec(algorithm="astar", heuristic="manhattan"),
    ]


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
    path: list[Cell]
    expansion_order: list[Cell]


class CompareOut(BaseModel):
    tick: int
    source: Cell
    target_id: str
    goal: Cell
    runs: list[SearchRunOut]


@router.post("/compare", responses={409: {"model": ErrorOut}})
async def search_compare(body: CompareIn) -> CompareOut:
    """Run algorithms x heuristics on the same problem (agent -> person at the chosen tick)."""
    sim = store.session(body.session_id).sim
    tick = sim.head.tick if body.tick is None else body.tick
    if not 0 <= tick <= sim.head.tick:
        raise HTTPException(404, f"tick {tick} is outside 0..{sim.head.tick}")
    snap = sim.history[tick]
    state = snap.state
    waiting = [p for p in state.people if p.status is Status.WAITING]
    wanted = body.target or snap.target or (waiting[0].id if waiting else None)
    person = next((p for p in waiting if p.id == wanted), None)
    if person is None:
        raise HTTPException(409, f"no waiting person {wanted!r} to search for at tick {tick}")
    problem = GridProblem(state, state.agent.pos, {person.pos}, sim.scenario.params.cost_model)
    specs = [
        (r.algorithm, r.heuristic or ("manhattan" if r.algorithm == "astar" else None))
        for r in body.runs
    ]
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
            path=list(r.result.path),
            expansion_order=list(r.result.expansion_order),
        )
        for r in compare(problem, specs)
    ]
    return CompareOut(
        tick=tick, source=state.agent.pos, target_id=person.id, goal=person.pos, runs=runs
    )
