from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def start(client: TestClient) -> Callable[..., dict[str, Any]]:
    def _start(scenario_id: str, **body: Any) -> dict[str, Any]:
        r = client.post("/simulation/start", json={"scenario_id": scenario_id, **body})
        assert r.status_code == 200, r.text
        data: dict[str, Any] = r.json()
        return data

    return _start
