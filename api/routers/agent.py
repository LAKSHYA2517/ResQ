from fastapi import APIRouter
from pydantic import BaseModel, Field

from resq.agent.baselines import benchmark
from resq.agent.profile import AGENT_TYPE, PEAS, environment
from resq.world.scenarios import random_scenario

from ..schemas import ErrorOut
from ..sessions import store

router = APIRouter(prefix="/agent", tags=["agent"], responses={404: {"model": ErrorOut}})


class PropertyOut(BaseModel):
    dimension: str
    value: str
    why: str


class ProfileOut(BaseModel):
    agent_type: str
    peas: dict[str, list[str]]
    environment: list[PropertyOut]  # derived from this scenario's parameters


@router.get("/profile")
async def profile(scenario_id: str | None = None, session_id: str | None = None) -> ProfileOut:
    """PEAS and the environment's properties for a scenario (or for a running session, whose
    fire mode may differ from the scenario file)."""
    scenario = (
        store.session(session_id).sim.scenario if session_id else store.scenario(scenario_id or "")
    )
    return ProfileOut(
        agent_type=AGENT_TYPE,
        peas={k: list(v) for k, v in PEAS.items()},
        environment=[PropertyOut(**vars(p)) for p in environment(scenario)],
    )


bench_router = APIRouter(prefix="/bench", tags=["bench"])


class BenchIn(BaseModel):
    scenario_ids: list[str] | None = None  # default: every predefined scenario
    random: int = Field(20, ge=0, le=100)  # plus this many seeded random scenarios
    seed: int = 1


class BenchRowOut(BaseModel):
    agent: str
    scenario: str
    rescued: int
    people: int
    cost: float
    ticks: int
    replans: int
    finished: bool


class BenchSummaryOut(BaseModel):
    agent: str
    scenarios: int
    rescued: int
    people: int
    rescued_pct: float
    mean_cost: float
    mean_ticks: float
    cost_per_rescue: float | None
    replans: int


class BenchOut(BaseModel):
    summaries: list[BenchSummaryOut]
    rows: list[BenchRowOut]
    expected_order_holds: bool  # utility >= goal-based >= reflex in people rescued


@bench_router.post("/agents", responses={404: {"model": ErrorOut}})
async def bench_agents(body: BenchIn) -> BenchOut:
    """Simple-reflex vs goal-based vs utility-based agents on identical, seeded scenarios."""
    ids = body.scenario_ids if body.scenario_ids is not None else list(store.predefined)
    scenarios = [store.scenario(i) for i in ids]
    scenarios += [random_scenario(body.seed + i) for i in range(body.random)]
    rows, summaries = benchmark(scenarios)
    pct = {s.agent: s.rescued_pct for s in summaries}
    return BenchOut(
        summaries=[BenchSummaryOut(**vars(s)) for s in summaries],
        rows=[BenchRowOut(**vars(r)) for r in rows],
        expected_order_holds=pct["utility"] >= pct["goal"] >= pct["reflex"],
    )
