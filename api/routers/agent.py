from fastapi import APIRouter
from pydantic import BaseModel

from resq.agent.profile import AGENT_TYPE, PEAS, environment

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
