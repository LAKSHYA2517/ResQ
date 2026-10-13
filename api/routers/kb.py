from fastapi import APIRouter
from pydantic import BaseModel

from resq.logic.rules import CORE_RULES

router = APIRouter(prefix="/kb", tags=["kb"])


class RuleOut(BaseModel):
    name: str
    text: str
    body: list[str]
    head: str


@router.get("/rules")
async def rules() -> list[RuleOut]:
    """The Horn rules the agent reasons with, exactly as the engine holds them."""
    return [
        RuleOut(name=r.name, text=str(r), body=[str(a) for a in r.body], head=str(r.head))
        for r in CORE_RULES
    ]
