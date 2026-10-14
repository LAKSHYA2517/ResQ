from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import resq

from .routers import agent, bayes, kb, optimize, plan, scenario, search, simulation
from .ws import router as ws_router

app = FastAPI(title="ResQ-AI", version=resq.__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Health(BaseModel):
    status: str
    version: str


@app.get("/health")
def health() -> Health:
    return Health(status="ok", version=resq.__version__)


app.include_router(scenario.router)
app.include_router(simulation.router)
app.include_router(kb.router)
app.include_router(search.router)
app.include_router(bayes.router)
app.include_router(optimize.router)
app.include_router(plan.router)
app.include_router(agent.router)
app.include_router(agent.bench_router)
app.include_router(ws_router)
