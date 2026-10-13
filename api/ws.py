"""WebSocket autoplay: streams a Snapshot per tick while the session is running.

Server -> client: ``{"type": "snapshot", "snapshot": SnapshotOut}``,
``{"type": "status", "running": bool, "speed": float}``, ``{"type": "finished"}``,
``{"type": "error", "detail": str}``.
Client -> server: ``{"cmd": "run", "speed"?: float}``, ``{"cmd": "pause"}``, ``{"cmd": "step"}``.
"""

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .schemas import snapshot_out
from .sessions import MAX_SPEED, MIN_SPEED, Session, store

router = APIRouter()
IDLE_POLL_S = 0.1


@router.websocket("/ws/simulation/{session_id}")
async def stream(ws: WebSocket, session_id: str) -> None:
    await ws.accept()
    session = store.sessions.get(session_id)
    if session is None:
        await ws.send_json({"type": "error", "detail": f"unknown session {session_id!r}"})
        await ws.close(code=4404)
        return

    commands: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def reader() -> None:
        try:
            while True:
                commands.put_nowait(await ws.receive_json())
        except (WebSocketDisconnect, ValueError, RuntimeError):
            commands.put_nowait(None)  # closed (or sent something unreadable): stop streaming

    task = asyncio.create_task(reader())
    sent = None  # the snapshot object last pushed to this client
    try:
        while True:
            head = session.sim.head
            if head is not sent:  # also catches changes made through the REST endpoints
                await ws.send_json({"type": "snapshot", "snapshot": _dump(session)})
                sent = head
                if head.finished and session.running:
                    session.running = False
                    await ws.send_json({"type": "finished"})
            delay = 1 / session.speed if session.running else IDLE_POLL_S
            try:
                command = await asyncio.wait_for(commands.get(), delay)
            except TimeoutError:
                if session.running:
                    session.sim.step()
                continue
            if command is None:
                break
            match command.get("cmd"):
                case "run":
                    speed = command.get("speed", session.speed)
                    if isinstance(speed, int | float):
                        session.speed = min(MAX_SPEED, max(MIN_SPEED, float(speed)))
                    session.running = not session.sim.head.finished
                case "pause":
                    session.running = False
                case "step":
                    session.sim.step()
                case other:
                    await ws.send_json({"type": "error", "detail": f"unknown cmd {other!r}"})
            status = {"type": "status", "running": session.running, "speed": session.speed}
            await ws.send_json(status)
    except WebSocketDisconnect:
        pass
    finally:
        session.running = False  # ponytail: one viewer per session; autoplay stops when it leaves
        task.cancel()


def _dump(session: Session) -> dict[str, Any]:
    return snapshot_out(session.sim.head).model_dump(mode="json")
