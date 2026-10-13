from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from resq.agent.loop import Simulation
from resq.logic.rules import CORE_RULES
from resq.search import compare
from resq.search.problem import GridProblem
from resq.world.scenarios import load_all

Start = Callable[..., dict[str, Any]]


def test_rules_are_the_engines_core_rules(client: TestClient) -> None:
    rules = client.get("/kb/rules").json()
    assert [r["name"] for r in rules] == [r.name for r in CORE_RULES]
    hot = next(r for r in rules if r["name"] == "hot_zone")
    assert hot == {
        "name": "hot_zone",
        "text": "Adjacent(X, Y) & Fire(Y) -> Hot(X)",
        "body": ["Adjacent(X, Y)", "Fire(Y)"],
        "head": "Hot(X)",
    }


def test_search_compare_matches_a_direct_engine_run(client: TestClient, start: Start) -> None:
    sid = start("showcase")["session_id"]
    out = client.post(
        "/search/compare",
        json={
            "session_id": sid,
            "runs": [
                {"algorithm": "bfs"},
                {"algorithm": "ucs"},
                {"algorithm": "astar", "heuristic": "manhattan"},
                {"algorithm": "astar", "heuristic": "weighted"},
            ],
        },
    ).json()
    s = load_all()["showcase"]
    head = Simulation(s).head
    problem = GridProblem(
        head.state, head.state.agent.pos, {head.state.person("p2").pos}, s.params.cost_model
    )
    direct = {
        r.label: r.result
        for r in compare(
            problem, [("bfs", None), ("ucs", None), ("astar", "manhattan"), ("astar", "weighted")]
        )
    }
    assert out["target_id"] == "p2" and out["source"] == [4, 4] and out["goal"] == [7, 8]
    assert [r["label"] for r in out["runs"]] == list(direct)
    for run in out["runs"]:
        d = direct[run["label"]]
        assert (run["cost"], run["expanded"], run["generated"], run["max_frontier"]) == (
            d.cost,
            d.expanded,
            d.generated,
            d.max_frontier,
        )
        assert run["optimal_vs_ucs"] == d.optimal_vs_ucs
        assert [tuple(c) for c in run["path"]] == list(d.path)
        assert len(run["expansion_order"]) == run["expanded"]
    ucs = next(r for r in out["runs"] if r["label"] == "ucs")
    assert ucs["optimal_vs_ucs"] is True and ucs["steps"] == len(ucs["path"]) - 1


def test_search_compare_picks_other_targets_and_ticks(client: TestClient, start: Start) -> None:
    sid = start("showcase")["session_id"]
    p1 = client.post("/search/compare", json={"session_id": sid, "target": "p1"}).json()
    assert p1["target_id"] == "p1" and p1["goal"] == [1, 3]
    assert [r["label"] for r in p1["runs"]] == ["bfs", "ucs", "astar+manhattan"]
    assert p1["runs"][0]["optimal_vs_ucs"] is False  # BFS ignores rubble: really costlier
    client.post("/simulation/step", json={"session_id": sid})
    at0 = client.post("/search/compare", json={"session_id": sid, "tick": 0}).json()
    assert at0["tick"] == 0 and at0["source"] == [4, 4]
    now = client.post("/search/compare", json={"session_id": sid}).json()
    assert now["tick"] == 1 and now["source"] != [4, 4]


def test_search_compare_errors(client: TestClient, start: Start) -> None:
    sid = start("impossible")["session_id"]
    # Impossible: p1 is waiting but unreachable -> a found=False row, not an error
    run = client.post("/search/compare", json={"session_id": sid}).json()["runs"][0]
    assert run["found"] is False and run["cost"] is None and "no route" in run["reason"]
    assert (
        client.post("/search/compare", json={"session_id": sid, "target": "ghost"}).status_code
        == 409
    )
    assert client.post("/search/compare", json={"session_id": sid, "tick": 9}).status_code == 404
    assert client.post("/search/compare", json={"session_id": "nope"}).status_code == 404
    bad = {"session_id": sid, "runs": [{"algorithm": "dfs"}]}
    assert client.post("/search/compare", json=bad).status_code == 422
