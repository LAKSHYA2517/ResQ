from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest

from resq.world.scenarios import Scenario, load_all, parse_scenario

BASE: dict[str, Any] = {
    "name": "t",
    "grid_size": [5, 5],
    "agent": [0, 0],
    "people": [{"id": "p1", "pos": [3, 1], "risk": 2, "urgency": 2}],
    "fire": [],
    "exits": [{"id": "e1", "pos": [4, 4]}],
}


@pytest.fixture
def raw() -> dict[str, Any]:
    return deepcopy(BASE)


@pytest.fixture
def make_scenario() -> Callable[..., Scenario]:
    """``make_scenario(terrain=[...], fire=[...], ...)``: BASE with overrides, must be valid."""

    def make(**overrides: Any) -> Scenario:
        d = {**deepcopy(BASE), **overrides}
        scenario, issues = parse_scenario(d)
        assert scenario is not None, [str(i) for i in issues]
        return scenario

    return make


@pytest.fixture(scope="session")
def shipped() -> dict[str, Scenario]:
    return load_all()
