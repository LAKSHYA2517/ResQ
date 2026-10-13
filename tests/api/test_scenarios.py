from typing import Any

from fastapi.testclient import TestClient

VALID: dict[str, Any] = {
    "name": "Custom",
    "grid_size": [5, 5],
    "agent": [0, 0],
    "people": [{"id": "p1", "pos": [2, 2]}],
    "fire": [],
    "exits": [{"id": "e1", "pos": [4, 4]}],
}


def test_lists_the_nine_predefined_scenarios(client: TestClient) -> None:
    items = client.get("/scenarios").json()
    predefined = {i["id"]: i for i in items if i["predefined"]}
    assert len(predefined) == 9
    assert predefined["showcase"] == {
        "id": "showcase",
        "name": "Showcase",
        "predefined": True,
        "rows": 10,
        "cols": 10,
        "people": 3,
        "exits": 2,
        "p_spread": 0.04,
        "scripted_events": 0,
    }


def test_get_scenario_returns_full_json_with_defaults_filled_in(client: TestClient) -> None:
    body = client.get("/scenario/blocked_exit").json()
    s = body["scenario"]
    assert body["id"] == "blocked_exit" and body["predefined"]
    assert s["grid_size"] == [10, 10] and len(s["terrain"]) == 10
    assert s["scripted_events"] == [{"tick": 4, "type": "EXIT_BLOCKED", "args": {"exit": "e1"}}]
    assert s["params"]["weights"]["w_r"] == 5 and s["params"]["cost_model"]["rubble"] == 3
    assert client.get("/scenario/nope").status_code == 404


def test_validate_reports_issues_with_cells(client: TestClient) -> None:
    assert client.post("/scenario/validate", json=VALID).json() == {"valid": True, "issues": []}
    bad = {**VALID, "fire": [[2, 2]], "exits": []}
    out = client.post("/scenario/validate", json=bad).json()
    assert not out["valid"] and len(out["issues"]) == 2
    on_fire = next(i for i in out["issues"] if "fire cell" in i["message"])
    assert on_fire["cell"] == [2, 2] and on_fire["field"] == "people[0]"


def test_create_custom_scenario_then_simulate_it(client: TestClient) -> None:
    created = client.post("/scenario", json=VALID)
    assert created.status_code == 201
    sid = created.json()["id"]
    assert sid.startswith("custom-") and not created.json()["predefined"]
    assert any(i["id"] == sid for i in client.get("/scenarios").json())
    assert client.get(f"/scenario/{sid}").json()["scenario"]["name"] == "Custom"
    started = client.post("/simulation/start", json={"scenario_id": sid})
    assert started.status_code == 200 and started.json()["snapshot"]["target"] == "p1"


def test_create_rejects_invalid_scenario_with_the_issue_list(client: TestClient) -> None:
    r = client.post("/scenario", json={**VALID, "people": []})
    assert r.status_code == 422
    assert not r.json()["valid"] and "at least one person" in r.json()["issues"][0]["message"]
