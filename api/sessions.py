"""In-memory scenario and session store. The backend owns the authoritative state."""

from dataclasses import dataclass, replace
from uuid import uuid4

from fastapi import HTTPException

from resq.agent.loop import Simulation
from resq.world.scenarios import Scenario, load_all

DEFAULT_SPEED = 4.0  # ticks per second
MIN_SPEED, MAX_SPEED = 0.5, 60.0


@dataclass
class Session:
    id: str
    scenario_id: str
    sim: Simulation
    running: bool = False
    speed: float = DEFAULT_SPEED


class Store:
    def __init__(self) -> None:
        self.predefined: dict[str, Scenario] = load_all()
        self.custom: dict[str, Scenario] = {}
        self.sessions: dict[str, Session] = {}

    def scenario(self, scenario_id: str) -> Scenario:
        found = self.predefined.get(scenario_id) or self.custom.get(scenario_id)
        if found is None:
            raise HTTPException(404, f"unknown scenario {scenario_id!r}")
        return found

    def add_scenario(self, scenario: Scenario) -> str:
        scenario_id = f"custom-{uuid4().hex[:8]}"
        self.custom[scenario_id] = scenario
        return scenario_id

    def start(self, scenario_id: str, seed: int | None) -> Session:
        scenario = self.scenario(scenario_id)
        if seed is not None:
            scenario = replace(scenario, seed=seed)
        session = Session(uuid4().hex[:12], scenario_id, Simulation(scenario))
        self.sessions[session.id] = session
        return session

    def session(self, session_id: str) -> Session:
        found = self.sessions.get(session_id)
        if found is None:
            raise HTTPException(404, f"unknown session {session_id!r}")
        return found


store = Store()
