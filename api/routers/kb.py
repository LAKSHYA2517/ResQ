from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from resq.logic.backward import ProofNode, prove
from resq.logic.forward import forward_chain
from resq.logic.resolution import refute
from resq.logic.rules import CORE_RULES
from resq.logic.terms import ParseError, is_ground, parse_atom

from ..schemas import DerivationOut, ErrorOut
from ..sessions import snapshot_at

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


class QueryIn(BaseModel):
    session_id: str
    goal: str  # e.g. "AtRisk(p2)" or "Eligible(P)"
    tick: int | None = None


class ProofNodeOut(BaseModel):
    goal: str
    rule: str | None  # None: a base fact
    children: list["ProofNodeOut"]


class ProofOut(BaseModel):
    bindings: dict[str, str]
    tree: ProofNodeOut


class ResolutionStepOut(BaseModel):
    clause: str
    parent: str | None
    side: str | None
    side_name: str | None


class ResolutionOut(BaseModel):
    entailed: bool
    steps: list[ResolutionStepOut]
    resolvents: int
    reason: str


class ForwardOut(BaseModel):
    holds: bool  # some instance of the goal is in the forward-chained KB
    answers: list[dict[str, str]]  # variable bindings of every matching fact
    derivations: list[DerivationOut]  # for a ground goal: its support, premises first
    passes: int


class QueryOut(BaseModel):
    goal: str
    ground: bool
    forward: ForwardOut
    backward: list[ProofOut]
    backward_steps: int  # goals tried by SLD resolution
    resolution: ResolutionOut | None  # only for ground goals
    agree: bool  # the methods that ran gave the same yes/no answer


def _tree(node: ProofNode) -> ProofNodeOut:
    return ProofNodeOut(
        goal=str(node.goal), rule=node.rule, children=[_tree(c) for c in node.children]
    )


@router.post("/query", responses={404: {"model": ErrorOut}, 422: {"model": ErrorOut}})
async def query(body: QueryIn) -> QueryOut:
    """ "Prove it": answer one goal three independent ways from the same base facts: forward
    chaining (is it in the fixpoint?), backward chaining (proof tree) and, for ground goals,
    resolution refutation (each resolvent down to the empty clause)."""
    _, snap = snapshot_at(body.session_id, body.tick)
    try:
        goal = parse_atom(body.goal)
    except ParseError as err:
        raise HTTPException(422, f"cannot parse goal: {err}") from err
    base = snap.base_facts
    kb, trace = forward_chain(CORE_RULES, base)
    answers = kb.ask(goal)
    ground = is_ground(goal)
    proofs, steps = prove(CORE_RULES, base, goal)
    resolution = refute(CORE_RULES, base, goal)[0] if ground else None
    verdicts = {bool(answers), bool(proofs)} | ({resolution.entailed} if resolution else set())
    return QueryOut(
        goal=str(goal),
        ground=ground,
        forward=ForwardOut(
            holds=bool(answers),
            answers=[{v.name: str(t) for v, t in sorted(s.items(), key=str)} for s in answers],
            derivations=[
                DerivationOut(
                    fact=str(d.fact),
                    rule=d.rule,
                    bindings=dict(d.bindings),
                    premises=[str(p) for p in d.premises],
                    iteration=d.iteration,
                )
                for d in (kb.why(goal) if ground else ())
            ],
            passes=trace[-1].iterations,  # type: ignore[attr-defined]
        ),
        backward=[ProofOut(bindings=dict(p.bindings), tree=_tree(p.tree)) for p in proofs],
        backward_steps=len(steps),
        resolution=None
        if resolution is None
        else ResolutionOut(
            entailed=resolution.entailed,
            steps=[ResolutionStepOut(**vars(s)) for s in resolution.steps],
            resolvents=resolution.resolvents,
            reason=resolution.reason,
        ),
        agree=len(verdicts) == 1,
    )
