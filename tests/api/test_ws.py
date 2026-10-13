from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from api.schemas import snapshot_out
from resq.agent.loop import Simulation
from resq.world.scenarios import load_all

Start = Callable[..., dict[str, Any]]


def snapshots_until_finished(ws: Any) -> list[dict[str, Any]]:
    out = []
    while True:
        msg = ws.receive_json()
        if msg["type"] == "snapshot":
            out.append(msg["snapshot"])
        elif msg["type"] == "finished":
            return out


def test_autoplay_streams_every_tick_and_matches_the_engine(
    client: TestClient, start: Start
) -> None:
    sid = start("basic_rescue")["session_id"]
    with client.websocket_connect(f"/ws/simulation/{sid}") as ws:
        first = ws.receive_json()
        assert first["type"] == "snapshot" and first["snapshot"]["tick"] == 0
        ws.send_json({"cmd": "run", "speed": 60})
        assert ws.receive_json() == {"type": "status", "running": True, "speed": 60.0}
        streamed = snapshots_until_finished(ws)
    sim = Simulation(load_all()["basic_rescue"])
    sim.run()
    assert [s["tick"] for s in streamed] == list(range(1, sim.head.tick + 1))  # none skipped
    expected = snapshot_out(sim.head).model_dump(mode="json")
    last = streamed[-1]
    assert last["status"] == "complete" and last["finished"]
    assert last["state"] == expected["state"] and last["plan"] == expected["plan"]
    assert {**last["metrics"], "timings_ms": {}} == {**expected["metrics"], "timings_ms": {}}
    state = client.get("/simulation/state", params={"session_id": sid}).json()
    assert state["tick"] == sim.head.tick


def test_step_pause_and_bad_commands(client: TestClient, start: Start) -> None:
    sid = start("multiple_people")["session_id"]
    with client.websocket_connect(f"/ws/simulation/{sid}") as ws:
        assert ws.receive_json()["snapshot"]["tick"] == 0
        ws.send_json({"cmd": "step"})
        assert ws.receive_json() == {"type": "status", "running": False, "speed": 4.0}
        assert ws.receive_json()["snapshot"]["tick"] == 1
        ws.send_json({"cmd": "dance"})
        assert ws.receive_json() == {"type": "error", "detail": "unknown cmd 'dance'"}
        assert ws.receive_json()["type"] == "status"
        ws.send_json({"cmd": "run", "speed": 60})
        assert ws.receive_json()["running"] is True
        assert ws.receive_json()["snapshot"]["tick"] == 2
        ws.send_json({"cmd": "pause"})
        while (msg := ws.receive_json())["type"] != "status":
            pass
        assert msg["running"] is False


def test_rest_changes_are_pushed_to_the_viewer(client: TestClient, start: Start) -> None:
    sid = start("basic_rescue")["session_id"]
    with client.websocket_connect(f"/ws/simulation/{sid}") as ws:
        assert ws.receive_json()["snapshot"]["tick"] == 0
        client.post("/simulation/step", json={"session_id": sid})
        assert ws.receive_json()["snapshot"]["tick"] == 1
        client.post(
            "/simulation/event",
            json={"session_id": sid, "type": "NEW_FIRE", "args": {"pos": [9, 0]}},
        )
        pushed = ws.receive_json()["snapshot"]
        assert pushed["tick"] == 1 and [9, 0] in pushed["state"]["fire"]


def test_unknown_session_gets_an_error_then_close(client: TestClient) -> None:
    with client.websocket_connect("/ws/simulation/nope") as ws:
        assert ws.receive_json() == {"type": "error", "detail": "unknown session 'nope'"}
