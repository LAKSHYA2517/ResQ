from random import Random
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from resq.uncertainty.bayesnet import BayesNet
from resq.uncertainty.exact import elimination, enumeration
from resq.uncertainty.models import risk_from_posterior, sensor_network
from resq.uncertainty.sampling import SAMPLERS

from ..schemas import ErrorOut

router = APIRouter(prefix="/bayes", tags=["bayes"])

SamplerName = Literal["rejection", "likelihood_weighting", "gibbs"]


class CptRow(BaseModel):
    given: list[bool]  # parent values, in the order of `parents`
    p_true: float


class NodeModel(BaseModel):
    name: str
    parents: list[str]
    cpt: list[CptRow]


class NetworkModel(BaseModel):
    nodes: list[NodeModel]


@router.get("/network")
async def network(prior: float = 0.2) -> NetworkModel:
    """The default per-zone sensor network: Fire -> Smoke, Heat, Trapped; Trapped -> Voice."""
    return NetworkModel.model_validate(sensor_network(min(1.0, max(0.0, prior))).to_dict())


class InferIn(BaseModel):
    network: NetworkModel | None = None  # default: the sensor network with `prior`
    prior: float = Field(0.2, ge=0, le=1)
    query: str = "Trapped"
    evidence: dict[str, bool] = {}
    samples: int = Field(5000, ge=1, le=200_000)
    seed: int = 0
    methods: list[SamplerName] = ["rejection", "likelihood_weighting", "gibbs"]


class ExactOut(BaseModel):
    method: str
    p_true: float
    work: int
    time_ms: float


class CurvePoint(BaseModel):
    n: int
    estimate: float
    error: float  # |estimate - exact|


class SampledOut(BaseModel):
    method: str
    p_true: float | None  # None: no sample matched the evidence
    error: float | None
    samples: int
    used: float
    time_ms: float
    curve: list[CurvePoint]


class InferOut(BaseModel):
    network: NetworkModel
    query: str
    evidence: dict[str, bool]
    exact: list[ExactOut]  # enumeration and variable elimination (they must agree)
    p_true: float
    risk: int  # round(5 * p_true): what the agent would use if the query is Trapped
    sampled: list[SampledOut]


@router.post("/infer", responses={422: {"model": ErrorOut}})
async def infer(body: InferIn) -> InferOut:
    """Exact posterior two ways, and sampling estimates with their convergence towards it."""
    try:
        raw: dict[str, Any] | None = body.network.model_dump() if body.network else None
        bn = BayesNet.from_dict(raw) if raw else sensor_network(body.prior)
        exact = [enumeration(bn, body.query, body.evidence)[0]]
        exact.append(elimination(bn, body.query, body.evidence)[0])
    except ValueError as err:
        raise HTTPException(422, str(err)) from err
    truth = exact[1].p_true
    sampled = []
    for name in body.methods:
        r, _ = SAMPLERS[name](bn, body.query, body.evidence, body.samples, Random(body.seed))
        sampled.append(
            SampledOut(
                method=r.method,
                p_true=r.p_true,
                error=None if r.p_true is None else abs(r.p_true - truth),
                samples=r.samples,
                used=r.used,
                time_ms=r.time_ms,
                curve=[CurvePoint(n=n, estimate=e, error=abs(e - truth)) for n, e in r.curve],
            )
        )
    return InferOut(
        network=NetworkModel.model_validate(bn.to_dict()),
        query=body.query,
        evidence=body.evidence,
        exact=[
            ExactOut(method=e.method, p_true=e.p_true, work=e.work, time_ms=e.time_ms)
            for e in exact
        ],
        p_true=truth,
        risk=risk_from_posterior(truth),
        sampled=sampled,
    )
