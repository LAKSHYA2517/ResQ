"""P4 endpoints: each is checked against a direct call into the engine."""

from collections.abc import Callable
from random import Random
from typing import Any

import pytest
from fastapi.testclient import TestClient

from resq.agent.loop import Simulation
from resq.agent.profile import environment
from resq.logic.forward import forward_chain
from resq.logic.rules import CORE_RULES
from resq.logic.terms import parse_atom
from resq.uncertainty.exact import elimination
from resq.uncertainty.models import sensor_network
from resq.uncertainty.sampling import likelihood_weighting
from resq.world.scenarios import load_all

Start = Callable[..., dict[str, Any]]
ALL = ["bfs", "dfs", "dls", "iddfs", "ucs", "greedy", "astar", "weighted_astar"]


def test_snapshot_carries_beliefs_and_start_can_switch_fire_mode(
    client: TestClient, start: Start
) -> None:
    data = start("showcase")
    assert data["fire_mode"] == "stochastic"
    beliefs = {b["person_id"]: b for b in data["snapshot"]["beliefs"]}
    head = Simulation(load_all()["showcase"]).head
    for b in head.beliefs:
        assert beliefs[b.person_id]["p_trapped"] == b.p_trapped
        assert beliefs[b.person_id]["evidence"] == dict(b.evidence)
        assert beliefs[b.person_id]["risk"] == b.risk
    worst = start("showcase", fire_mode="adversarial")
    assert worst["fire_mode"] == "adversarial"
    sid = worst["session_id"]
    for _ in range(4):
        snap = client.post("/simulation/step", json={"session_id": sid}).json()
    assert any(t["kind"] == "GameSearched" for t in snap["trace"])
    assert (
        client.post(
            "/simulation/start", json={"scenario_id": "showcase", "fire_mode": "x"}
        ).status_code
        == 422
    )


def test_all_eight_algorithms_compare(client: TestClient, start: Start) -> None:
    sid = start("showcase")["session_id"]
    body = {"session_id": sid, "runs": [{"algorithm": a} for a in ALL], "limit": 12, "w": 3}
    out = client.post("/search/compare", json=body).json()
    rows = {r["algorithm"]: r for r in out["runs"]}
    assert set(rows) == set(ALL) and all(r["found"] for r in rows.values())
    assert rows["dls"]["label"] == "dls(limit=12)" and rows["dls"]["depth_limit"] == 12
    assert rows["weighted_astar"]["label"] == "weighted_astar(w=3)+manhattan"
    assert rows["greedy"]["heuristic"] == "manhattan" and rows["dfs"]["heuristic"] is None
    assert rows["astar"]["optimal_vs_ucs"] and rows["ucs"]["optimal_vs_ucs"]
    assert rows["iddfs"]["steps"] == rows["bfs"]["steps"]
    for r in rows.values():
        assert r["optimal_vs_ucs"] == (r["cost"] == rows["ucs"]["cost"])
    cut = client.post(
        "/search/compare", json={"session_id": sid, "runs": [{"algorithm": "dls"}], "limit": 2}
    ).json()["runs"][0]
    assert not cut["found"] and cut["reason"].startswith("cutoff")


def test_heuristic_check(client: TestClient, start: Start) -> None:
    sid = start("showcase")["session_id"]
    good = client.post("/search/heuristic-check", json={"session_id": sid}).json()
    assert good["admissible"] and good["consistent"] and good["astar"]["optimal_vs_ucs"]
    assert good["admissibility_violations"] == [] and good["goal"] == [7, 8]
    bad = client.post(
        "/search/heuristic-check", json={"session_id": sid, "heuristic": "weighted", "w": 4}
    ).json()
    assert not bad["admissible"] and not bad["consistent"]
    assert bad["n_admissibility_violations"] >= len(bad["admissibility_violations"]) > 0
    v = bad["admissibility_violations"][0]
    assert v["h"] > v["true_cost"]
    c = bad["consistency_violations"][0]
    assert c["h"] > c["step_cost"] + c["h_next"]
    assert bad["astar"]["expanded"] <= good["astar"]["expanded"]


def test_kb_query_ground_goal_three_ways(client: TestClient, start: Start) -> None:
    sid = start("showcase")["session_id"]
    out = client.post("/kb/query", json={"session_id": sid, "goal": "RescueNow(p2)"}).json()
    assert out["ground"] and out["agree"] and out["forward"]["holds"]
    assert out["forward"]["derivations"][-1]["fact"] == "RescueNow(p2)"
    tree = out["backward"][0]["tree"]
    assert tree["goal"] == "RescueNow(p2)" and tree["rule"] == "rescue_now"
    assert [c["goal"] for c in tree["children"]] == ["Eligible(p2)", "Critical(p2)"]
    res = out["resolution"]
    assert res["entailed"] and res["steps"][0]["clause"] == "¬RescueNow(p2)"
    assert res["steps"][-1]["clause"] == "□" and res["resolvents"] >= len(res["steps"]) - 1
    # agrees with a direct forward-chaining run on the same snapshot
    head = Simulation(load_all()["showcase"]).head
    kb, _ = forward_chain(CORE_RULES, head.base_facts)
    assert kb.holds(parse_atom("RescueNow(p2)"))


def test_kb_query_false_goal_and_variables(client: TestClient, start: Start) -> None:
    sid = start("showcase")["session_id"]
    no = client.post("/kb/query", json={"session_id": sid, "goal": "AtRisk(p1)"}).json()
    assert no["agree"] and not no["forward"]["holds"] and no["backward"] == []
    assert not no["resolution"]["entailed"] and "saturated" in no["resolution"]["reason"]
    who = client.post("/kb/query", json={"session_id": sid, "goal": "Eligible(P)"}).json()
    assert not who["ground"] and who["resolution"] is None and who["agree"]
    assert sorted(a["P"] for a in who["forward"]["answers"]) == ["p1", "p2", "p3"]
    assert sorted(p["bindings"]["P"] for p in who["backward"]) == ["p1", "p2", "p3"]
    bad = client.post("/kb/query", json={"session_id": sid, "goal": "AtRisk(p2"})
    assert bad.status_code == 422 and "cannot parse goal" in bad.json()["detail"]
    assert client.post("/kb/query", json={"session_id": "nope", "goal": "A(b)"}).status_code == 404


def test_bayes_infer_exact_and_convergence(client: TestClient) -> None:
    evidence = {"Smoke": True, "Heat": True, "Voice": False}
    body = {"prior": 0.4, "evidence": evidence, "samples": 20000, "seed": 5}
    out = client.post("/bayes/infer", json=body).json()
    bn = sensor_network(0.4)
    truth = elimination(bn, "Trapped", evidence)[0].p_true
    assert out["p_true"] == truth and out["risk"] == int(5 * truth + 0.5)
    assert [e["method"] for e in out["exact"]] == ["enumeration", "elimination"]
    assert out["exact"][0]["p_true"] == pytest.approx(out["exact"][1]["p_true"], abs=1e-12)
    lw = next(s for s in out["sampled"] if s["method"] == "likelihood_weighting")
    direct, _ = likelihood_weighting(bn, "Trapped", evidence, 20000, Random(5))
    assert lw["p_true"] == direct.p_true and lw["error"] == abs((direct.p_true or 0) - truth)
    assert lw["curve"][-1] == {"n": 20000, "estimate": lw["p_true"], "error": lw["error"]}
    for s in out["sampled"]:
        assert s["error"] < 0.03 and len(s["curve"]) > 10
    assert len(out["network"]["nodes"]) == 5


def test_bayes_custom_network_and_errors(client: TestClient) -> None:
    net = client.get("/bayes/network", params={"prior": 0.3}).json()
    fire = next(n for n in net["nodes"] if n["name"] == "Fire")
    assert fire["cpt"] == [{"given": [], "p_true": 0.3}]
    fire["cpt"][0]["p_true"] = 1.0  # edit the CPT: fire is certain
    out = client.post("/bayes/infer", json={"network": net, "query": "Fire", "samples": 100}).json()
    assert out["p_true"] == 1.0
    fire["cpt"][0]["p_true"] = 1.7
    bad = client.post("/bayes/infer", json={"network": net})
    assert bad.status_code == 422 and "not a probability" in bad.json()["detail"]
    unknown = client.post("/bayes/infer", json={"query": "Aliens"})
    assert unknown.status_code == 422 and "unknown variable" in unknown.json()["detail"]


def test_optimize_order(client: TestClient, start: Start) -> None:
    sid = start("mass_evacuation")["session_id"]
    out = client.post("/optimize/order", json={"session_id": sid, "seed": 3}).json()
    assert len(out["people"]) == 7 and out["skipped"] == []
    rows = {r["method"]: r for r in out["rows"]}
    assert (
        rows["exhaustive"]["cost"] == out["optimum"] and rows["exhaustive"]["evaluations"] == 5040
    )
    for r in out["rows"]:
        assert r["gap"] == pytest.approx(r["cost"] - out["optimum"]) and r["gap"] >= -1e-9
        assert sorted(r["order"]) == sorted(p["id"] for p in out["people"])
        assert r["curve"][-1] == r["cost"]
    assert rows["greedy"]["gap"] > 0
    again = client.post("/optimize/order", json={"session_id": sid, "seed": 3}).json()
    assert [r["cost"] for r in again["rows"]] == [r["cost"] for r in out["rows"]]
    stuck = start("impossible")["session_id"]
    none = client.post("/optimize/order", json={"session_id": stuck}).json()
    assert none["people"] == [] and none["skipped"] == ["p1: no route from the agent"]


def test_adversarial_move(client: TestClient, start: Start) -> None:
    sid = start("showcase")["session_id"]
    out = client.post("/adversarial/move", json={"session_id": sid, "depth": 4}).json()
    assert out["same_move"] and out["same_value"]
    assert out["alphabeta"]["nodes"] < out["minimax"]["nodes"]
    assert out["nodes_saved"] == out["minimax"]["nodes"] - out["alphabeta"]["nodes"] > 0
    assert out["minimax"]["cutoffs"] == 0 and out["alphabeta"]["cutoffs"] > 0
    assert out["source"] == [4, 4] and out["goal"] == [7, 8] and out["calm_cost"] == 13
    assert out["minimax"]["value"] >= out["calm_cost"]
    assert out["minimax"]["line"][0] == [out["minimax"]["move"]]
    stuck = start("impossible")["session_id"]
    assert client.post("/adversarial/move", json={"session_id": stuck}).status_code == 409
    assert client.post("/adversarial/move", json={"session_id": sid, "depth": 9}).status_code == 422


def test_plan_compare(client: TestClient, start: Start) -> None:
    sid = start("multiple_people")["session_id"]
    one = client.post("/plan/compare", json={"session_id": sid}).json()
    assert one["people"] == ["p3"] and one["goal"] == ["Evacuated(p3)"] and one["equal_cost"]
    assert len({r["cost"] for r in one["rows"]}) == 1 and len(one["rows"]) == 4
    assert one["rows"][0]["steps"] == one["rows"][2]["steps"]  # forward and regression agree
    everyone = client.post("/plan/compare", json={"session_id": sid, "scope": "all"}).json()
    assert sorted(everyone["people"]) == ["p1", "p2", "p3"] and everyone["equal_cost"]
    by = {r["planner"]: r for r in everyone["rows"]}
    assert by["forward A* (admissible h)"]["expanded"] <= by["forward uniform-cost"]["expanded"]
    assert by["regression + domain pruning"]["expanded"] < by["regression (plain)"]["expanded"]
    assert len(by["forward A* (admissible h)"]["steps"]) == 12
    crowd = start("mass_evacuation")["session_id"]
    capped = client.post("/plan/compare", json={"session_id": crowd, "scope": "all"}).json()
    assert len(capped["people"]) == 4 and "highest-priority" in capped["note"]
    stuck = start("impossible")["session_id"]
    assert client.post("/plan/compare", json={"session_id": stuck}).status_code == 409


def test_agent_profile_follows_the_scenario(client: TestClient, start: Start) -> None:
    calm = client.get("/agent/profile", params={"scenario_id": "basic_rescue"}).json()
    env = {p["dimension"]: p["value"] for p in calm["environment"]}
    assert env["Deterministic"] == "Deterministic" and env["Static"] == "Static"
    assert env["Agents"] == "Single agent" and set(calm["peas"]) == {
        "Performance", "Environment", "Actuators", "Sensors",
    }  # fmt: skip
    spreading = client.get("/agent/profile", params={"scenario_id": "showcase"}).json()
    env = {p["dimension"]: p["value"] for p in spreading["environment"]}
    assert env["Deterministic"] == "Stochastic" and env["Static"] == "Dynamic"
    sid = start("showcase", fire_mode="adversarial")["session_id"]
    worst = client.get("/agent/profile", params={"session_id": sid}).json()
    env = {p["dimension"]: p["value"] for p in worst["environment"]}
    assert env["Agents"] == "Multi-agent (competitive)" and env["Deterministic"] == "Strategic"
    expected = environment(load_all()["showcase"])
    assert [p["why"] for p in spreading["environment"]] == [p.why for p in expected]
    assert client.get("/agent/profile", params={"scenario_id": "nope"}).status_code == 404
