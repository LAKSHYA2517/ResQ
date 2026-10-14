"""REST simulation endpoints. Every assertion compares the API with a direct engine run:
the API must add nothing and lose nothing."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from api.schemas import snapshot_out
from resq.agent.loop import Simulation
from resq.world.events import EventType
from resq.world.scenarios import load_all

Start = Callable[..., dict[str, Any]]


def dump(sim: Simulation) -> dict[str, Any]:
    return strip(snapshot_out(sim.head).model_dump(mode="json"))


def strip(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Wall-clock timings are the only non-deterministic part of a snapshot."""
    return {**snapshot, "metrics": {**snapshot["metrics"], "timings_ms": {}}}


def test_start_returns_the_engines_first_snapshot(client: TestClient, start: Start) -> None:
    data = start("showcase")
    snap = data["snapshot"]
    assert data["scenario_id"] == "showcase" and data["seed"] == 24
    assert strip(snap) == dump(Simulation(load_all()["showcase"]))
    assert snap["tick"] == 0 and snap["status"] == "running" and snap["target"] == "p2"
    assert [s["status"] for s in snap["plan"]] == ["current", "pending", "pending", "pending"]
    assert snap["plan"][0]["label"] == "Travel(c4_4, c7_8)"
    assert snap["route"][0] == [4, 4] and snap["route"][-1] == [7, 8]
    assert snap["priorities"][0]["breakdown"] == "p2: 5×5 + 3×4 − 1×13 = 24"
    assert snap["state"]["terrain"][0][5] == "wall" and snap["state"]["terrain"][0][9] == "exit"
    assert snap["state"]["hot"] and all(e["usable"] for e in snap["state"]["exits"])
    assert not any(f.startswith("Adjacent") for f in snap["facts"])
    assert snap["fact_counts"]["Adjacent"] > 100 and snap["fact_counts"]["Fire"] == 1
    at_risk = next(d for d in snap["derived"] if d["fact"] == "AtRisk(p2)")
    assert at_risk["rule"] == "at_risk" and at_risk["bindings"] == {"P": "p2", "X": "c7_8"}
    assert at_risk["premises"] == ["Person(p2, c7_8)", "Unsafe(c7_8)"]
    assert {t["kind"] for t in snap["trace"]} >= {"RouteComputed", "PlanFound", "PlanAdopted"}
    assert snap["metrics"]["timings_ms"]["total"] > 0


def test_step_matches_the_engine_tick_for_tick(client: TestClient, start: Start) -> None:
    sid = start("dynamic_emergency")["session_id"]
    sim = Simulation(load_all()["dynamic_emergency"])
    for _ in range(6):
        sim.step()
        got = client.post("/simulation/step", json={"session_id": sid}).json()
        assert strip(got) == dump(sim)
    assert strip(client.get("/simulation/state", params={"session_id": sid}).json()) == dump(sim)
    at3 = client.get("/simulation/replay/3", params={"session_id": sid}).json()
    assert at3["replan_reason"] == "Travel(c1_1, c7_7): route cell (4, 4) is now on fire"
    assert at3["plan_change"]["kind"] == "invalid" and at3["plan_change"]["is_replan"]
    assert at3["plan_change"]["old_steps"][0] == "Travel(c1_1, c7_7)"


def test_seed_override_changes_the_run(client: TestClient, start: Start) -> None:
    a = start("spreading_fire", seed=1)
    b = start("spreading_fire", seed=2)
    assert (a["seed"], b["seed"]) == (1, 2)
    fires = []
    for data in (a, b):
        for _ in range(15):
            snap = client.post("/simulation/step", json={"session_id": data["session_id"]}).json()
        fires.append(snap["state"]["fire"])
    assert fires[0] != fires[1]


def test_event_returns_fact_diff_and_replan_reason(client: TestClient, start: Start) -> None:
    data = start("basic_rescue")
    sid, route = data["session_id"], data["snapshot"]["route"]
    target_cell = route[3]
    r = client.post(
        "/simulation/event",
        json={"session_id": sid, "type": "NEW_FIRE", "args": {"pos": target_cell}},
    )
    assert r.status_code == 200
    out = r.json()
    name = f"c{target_cell[0]}_{target_cell[1]}"
    assert out["snapshot"]["tick"] == 0  # the event belongs to the current tick
    assert f"Fire({name})" in out["diff"]["added"] and f"Unsafe({name})" in out["diff"]["added"]
    assert out["diff"]["removed"] == []
    assert out["replan_reason"] == out["snapshot"]["replan_reason"]
    assert f"route cell ({target_cell[0]}, {target_cell[1]}) is now on fire" in out["replan_reason"]
    assert target_cell not in out["snapshot"]["route"]
    assert target_cell in out["snapshot"]["state"]["fire"]

    sim = Simulation(load_all()["basic_rescue"])
    sim.inject(EventType.NEW_FIRE, {"pos": target_cell})
    assert strip(out["snapshot"]) == dump(sim)

    gone = client.post(
        "/simulation/event",
        json={"session_id": sid, "type": "FIRE_EXTINGUISHED", "args": {"pos": target_cell}},
    ).json()
    assert f"Fire({name})" in gone["diff"]["removed"] and gone["diff"]["added"] == []


def test_conflicting_event_is_a_409_with_the_reason(client: TestClient, start: Start) -> None:
    sid = start("basic_rescue")["session_id"]
    before = client.get("/simulation/state", params={"session_id": sid}).json()
    r = client.post(
        "/simulation/event",
        json={"session_id": sid, "type": "NEW_FIRE", "args": {"pos": [0, 0]}},
    )
    assert r.status_code == 409 and "agent is standing there" in r.json()["detail"]
    after = client.get("/simulation/state", params={"session_id": sid}).json()
    assert strip(after) == strip(before)
    bad_type = client.post("/simulation/event", json={"session_id": sid, "type": "FIRE_SPREAD"})
    assert bad_type.status_code == 422  # automatic events cannot be injected


def test_replay_fresh_rebuilds_the_same_snapshot_from_the_log(
    client: TestClient, start: Start
) -> None:
    sid = start("showcase")["session_id"]
    for i in range(12):
        snap = client.post("/simulation/step", json={"session_id": sid}).json()
        if i == 4:
            client.post(
                "/simulation/event",
                json={"session_id": sid, "type": "NEW_FIRE", "args": {"pos": snap["route"][2]}},
            )
    for tick in (0, 5, 9, 12):
        stored = client.get(f"/simulation/replay/{tick}", params={"session_id": sid}).json()
        fresh = client.get(
            f"/simulation/replay/{tick}", params={"session_id": sid, "fresh": True}
        ).json()
        assert stored["tick"] == tick and strip(fresh) == strip(stored)
    assert client.get("/simulation/replay/13", params={"session_id": sid}).status_code == 404
    assert client.get("/simulation/replay/-1", params={"session_id": sid}).status_code == 404


def test_reset_goes_back_to_tick_zero(client: TestClient, start: Start) -> None:
    data = start("basic_rescue")
    sid = data["session_id"]
    for _ in range(3):
        client.post("/simulation/step", json={"session_id": sid})
    client.post(
        "/simulation/event", json={"session_id": sid, "type": "NEW_FIRE", "args": {"pos": [9, 0]}}
    )
    reset = client.post("/simulation/reset", json={"session_id": sid}).json()
    assert strip(reset) == strip(data["snapshot"])


def test_impossible_scenario_is_reported_calmly(client: TestClient, start: Start) -> None:
    snap = start("impossible")["snapshot"]
    assert snap["status"] == "stuck" and snap["finished"]
    assert snap["plan"] == [] and snap["route"] == [] and snap["target"] is None
    assert "A* found no route" in snap["no_plan_reasons"][0]
    assert any(t["kind"] == "NoValidPlan" for t in snap["trace"])


def test_run_flag_and_unknown_ids(client: TestClient, start: Start) -> None:
    sid = start("basic_rescue")["session_id"]
    on = client.post("/simulation/run", params={"speed": 10}, json={"session_id": sid}).json()
    assert on == {"session_id": sid, "running": True, "speed": 10}
    off = client.post("/simulation/run", params={"speed": 0}, json={"session_id": sid}).json()
    assert off == {"session_id": sid, "running": False, "speed": 10}
    assert (
        client.post("/simulation/run", params={"speed": 999}, json={"session_id": sid}).status_code
        == 422
    )
    assert client.post("/simulation/step", json={"session_id": "nope"}).status_code == 404
    assert client.get("/simulation/state", params={"session_id": "nope"}).status_code == 404
    assert client.post("/simulation/start", json={"scenario_id": "nope"}).status_code == 404
    done = start("impossible")["session_id"]  # already finished: nothing to run
    assert not client.post("/simulation/run", json={"session_id": done}).json()["running"]


def test_log_lists_events_and_replan_reasons_from_the_trace(
    client: TestClient, start: Start
) -> None:
    sid = start("dynamic_emergency")["session_id"]
    for _ in range(4):
        client.post("/simulation/step", json={"session_id": sid})
    log = client.get("/simulation/log", params={"session_id": sid}).json()
    at3 = [e for e in log if e["tick"] == 3]
    kinds = [e["kind"] for e in at3]
    assert kinds.index("event") < kinds.index("replan") < kinds.index("plan")
    replan = next(e for e in at3 if e["kind"] == "replan")
    assert replan["reason"] == "Travel(c1_1, c7_7): route cell (4, 4) is now on fire"
    assert next(e for e in at3 if e["kind"] == "event")["text"].startswith("NEW_FIRE")
    assert all(e["kind"] != "action" or e["text"].startswith(("PickUp", "DropOff")) for e in log)


def test_run_report(client: TestClient, start: Start) -> None:
    sid = start("dynamic_emergency")["session_id"]
    for _ in range(4):
        client.post("/simulation/step", json={"session_id": sid})
    client.post(
        "/simulation/event",
        json={"session_id": sid, "type": "EXIT_BLOCKED", "args": {"exit": "e1"}},
    )
    rep = client.get("/simulation/report", params={"session_id": sid}).json()
    assert rep["scenario_id"] == "dynamic_emergency" and rep["ticks"] == 4 and rep["seed"] == 5
    assert rep["replay_identical"] is True
    assert rep["user_events"] == [{"tick": 4, "type": "EXIT_BLOCKED", "args": {"exit": "e1"}}]
    assert rep["replans"][0] == {
        "tick": 3,
        "kind": "invalid",
        "reason": "Travel(c1_1, c7_7): route cell (4, 4) is now on fire",
    }
    assert all(h["kind"] != "spread" for h in rep["highlights"])
    state = client.get("/simulation/state", params={"session_id": sid}).json()
    assert {**rep["metrics"], "timings_ms": {}} == {**state["metrics"], "timings_ms": {}}
    assert rep["people"] == [{"id": "p1", "status": "WAITING", "pos": [7, 7]}]
    assert client.get("/simulation/report", params={"session_id": "nope"}).status_code == 404
