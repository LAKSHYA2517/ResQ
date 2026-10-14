import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from resq.decision.ordering import build_order_problem, optimise
from resq.decision.priority import urgency
from resq.logic.terms import atom
from resq.search.adversarial import Decision, FireGame, FireMove, alphabeta, minimax
from resq.search.router import Router
from resq.world.state import Status

from ..schemas import Cell, ErrorOut
from ..sessions import snapshot_at

router = APIRouter(tags=["optimize"], responses={404: {"model": ErrorOut}})


class OrderIn(BaseModel):
    session_id: str
    tick: int | None = None
    seed: int | None = None  # default: the scenario's seed
    restarts: int = Field(5, ge=1, le=50)
    sa_steps: int = Field(600, ge=1, le=20_000)
    sa_alpha: float = Field(0.97, gt=0, lt=1)
    ga_population: int = Field(30, ge=2, le=300)
    ga_generations: int = Field(60, ge=1, le=1000)
    ga_mutation: float = Field(0.2, ge=0, le=1)


class OrderPerson(BaseModel):
    id: str
    weight: float  # w_r * Risk + w_u * Urgency
    exit: str  # nearest reachable exit (by A* cost)
    from_agent: float
    to_exit: float


class OrderRowOut(BaseModel):
    method: str
    order: list[str]
    cost: float
    evaluations: int
    gap: float | None  # cost minus the exhaustive optimum
    time_ms: float
    curve: list[float]  # best cost so far per iteration / generation


class OrderOut(BaseModel):
    tick: int
    people: list[OrderPerson]
    skipped: list[str]
    optimum: float | None  # None when there are too many people to enumerate
    rows: list[OrderRowOut]


@router.post("/optimize/order")
async def optimize_order(body: OrderIn) -> OrderOut:
    """Rescue-order optimisation: minimise the sum of weight x completion time, with hill
    climbing, simulated annealing and a genetic algorithm against greedy and the true optimum."""
    session, snap = snapshot_at(body.session_id, body.tick)
    scenario, state = session.sim.scenario, snap.state
    w = scenario.params.weights
    risk = {b.person_id: b.risk for b in snap.beliefs}
    weights = {
        p.id: w.w_r * risk.get(p.id, 0) + w.w_u * urgency(p.urgency, state.tick, w)
        for p in state.people
        if p.status is Status.WAITING
    }
    unavailable = {d.fact for d in snap.derived if d.fact.pred == "Unavailable"}
    open_exits = [e for e in state.exits if atom("Unavailable", e.id) not in unavailable]
    router_ = Router(state, scenario.params.cost_model)
    problem = build_order_problem(state, router_, weights, open_exits)
    report, _ = optimise(
        problem,
        scenario.seed if body.seed is None else body.seed,
        body.restarts,
        body.sa_steps,
        body.sa_alpha,
        body.ga_population,
        body.ga_generations,
        body.ga_mutation,
    )
    return OrderOut(
        tick=snap.tick,
        people=[
            OrderPerson(
                id=pid,
                weight=problem.weights[i],
                exit=problem.exits[i],
                from_agent=problem.from_start[i],
                to_exit=problem.carry[i],
            )
            for i, pid in enumerate(problem.people)
        ],
        skipped=list(problem.skipped),
        optimum=report.optimum,
        rows=[
            OrderRowOut(
                method=r.method,
                order=list(r.order),
                cost=r.cost,
                evaluations=r.evaluations,
                gap=r.gap,
                time_ms=r.time_ms,
                curve=list(r.curve),
            )
            for r in report.rows
        ],
    )


class AdversarialIn(BaseModel):
    session_id: str
    tick: int | None = None
    depth: int = Field(4, ge=1, le=6)  # plies: agent, fire, agent, ...
    k: int = Field(1, ge=1, le=2)  # cells the fire may ignite per turn


class GameResult(BaseModel):
    algorithm: str
    move: Cell | None  # the agent's best next cell
    value: float | None  # cost to finish the leg under worst-case fire; None = cut off
    cut_off: bool
    nodes: int
    cutoffs: int
    time_ms: float
    line: list[list[Cell]]  # principal variation: agent step, fire ignition(s), agent step, ...


class AdversarialOut(BaseModel):
    tick: int
    source: Cell
    goal: Cell
    depth: int
    k: int
    minimax: GameResult
    alphabeta: GameResult
    same_move: bool
    same_value: bool
    nodes_saved: int
    calm_cost: float | None  # A* cost if the fire did nothing (for comparison)


def _game_result(d: Decision[FireMove]) -> GameResult:
    cut = math.isinf(d.value)
    return GameResult(
        algorithm=d.algorithm,
        move=d.move[0] if d.move else None,
        value=None if cut else d.value,
        cut_off=cut,
        nodes=d.nodes,
        cutoffs=d.cutoffs,
        time_ms=d.time_ms,
        line=[list(m) for m in d.line],
    )


@router.post("/adversarial/move", responses={409: {"model": ErrorOut}})
async def adversarial_move(body: AdversarialIn) -> AdversarialOut:
    """The agent's best next step if the fire played its worst case, found by minimax and by
    alpha-beta on the same game: same move and value, fewer nodes with pruning."""
    session, snap = snapshot_at(body.session_id, body.tick)
    if len(snap.route) < 2:
        raise HTTPException(
            409, f"the agent is not travelling at tick {snap.tick}: no leg to attack"
        )
    costs = session.sim.scenario.params.cost_model
    goal = snap.route[-1]
    plain = FireGame(snap.state, goal, costs, body.k)  # separate games: no shared A* cache
    full, _ = minimax(plain, plain.root(), body.depth)
    game = FireGame(snap.state, goal, costs, body.k)
    pruned, _ = alphabeta(game, game.root(), body.depth)
    return AdversarialOut(
        tick=snap.tick,
        source=snap.state.agent.pos,
        goal=goal,
        depth=body.depth,
        k=body.k,
        minimax=_game_result(full),
        alphabeta=_game_result(pruned),
        same_move=full.move == pruned.move,
        same_value=full.value == pruned.value,
        nodes_saved=full.nodes - pruned.nodes,
        calm_cost=Router(snap.state, costs).route(snap.state.agent.pos, goal).cost,
    )
