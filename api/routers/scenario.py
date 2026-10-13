from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from resq.world.scenarios import parse_scenario

from ..schemas import (
    ErrorOut,
    ScenarioOut,
    ScenarioSummary,
    ValidationOut,
    scenario_out,
    scenario_summary,
    validation_out,
)
from ..sessions import store

router = APIRouter(tags=["scenario"])


@router.get("/scenarios")
async def list_scenarios() -> list[ScenarioSummary]:
    return [
        *(scenario_summary(sid, s, True) for sid, s in store.predefined.items()),
        *(scenario_summary(sid, s, False) for sid, s in store.custom.items()),
    ]


@router.get("/scenario/{scenario_id}", responses={404: {"model": ErrorOut}})
async def get_scenario(scenario_id: str) -> ScenarioOut:
    return scenario_out(scenario_id, store.scenario(scenario_id), scenario_id in store.predefined)


@router.post("/scenario/validate")
async def validate_scenario(scenario: dict[str, Any]) -> ValidationOut:
    """Body: scenario JSON (shape of ``ScenarioModel``). Accepts anything, so that every problem
    comes back as a readable issue with its cell instead of a schema error."""
    return validation_out(parse_scenario(scenario)[1])


@router.post(
    "/scenario",
    status_code=201,
    response_model=ScenarioOut,
    responses={422: {"model": ValidationOut}},
)
async def create_scenario(scenario: dict[str, Any]) -> ScenarioOut | JSONResponse:
    """Register a custom scenario for this server run (not written to disk)."""
    parsed, issues = parse_scenario(scenario)
    if parsed is None:
        return JSONResponse(validation_out(issues).model_dump(), status_code=422)
    return scenario_out(store.add_scenario(parsed), parsed, False)
