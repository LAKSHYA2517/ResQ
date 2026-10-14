from fastapi import APIRouter, HTTPException, Query

from resq.agent.loop import Snapshot, replay
from resq.trace import (
    ActionExecuted,
    EventApplied,
    EventRejected,
    FireSpread,
    NoValidPlan,
    PersonStatusChanged,
    PlanAdopted,
    PlanInvalidated,
)
from resq.world.events import EventError, EventType

from ..schemas import (
    ErrorOut,
    EventIn,
    EventOut,
    FactDiff,
    LogEntryOut,
    RunOut,
    SessionIn,
    SessionOut,
    SnapshotOut,
    StartIn,
    all_facts,
    snapshot_out,
)
from ..sessions import MAX_SPEED, MIN_SPEED, store

# Handlers are async on purpose: they then run on the event loop, so a REST call and the
# WebSocket autoplay can never step the same simulation at the same time.
router = APIRouter(prefix="/simulation", tags=["simulation"], responses={404: {"model": ErrorOut}})


@router.post("/start")
async def start(body: StartIn) -> SessionOut:
    session = store.start(body.scenario_id, body.seed, body.fire_mode)
    return SessionOut(
        session_id=session.id,
        scenario_id=session.scenario_id,
        seed=session.sim.scenario.seed,
        fire_mode=session.sim.scenario.params.fire_mode,  # type: ignore[arg-type]
        snapshot=snapshot_out(session.sim.head),
    )


@router.post("/step")
async def step(body: SessionIn) -> SnapshotOut:
    return snapshot_out(store.session(body.session_id).sim.step())


@router.post("/run")
async def run(body: SessionIn, speed: float = Query(4.0, ge=0, le=MAX_SPEED)) -> RunOut:
    """Start autoplay at ``speed`` ticks per second (``speed=0`` pauses). Snapshots are streamed
    on ``/ws/simulation/{id}``; autoplay only advances while a client is connected there."""
    session = store.session(body.session_id)
    session.running = speed > 0 and not session.sim.head.finished
    if speed > 0:
        session.speed = max(MIN_SPEED, speed)
    return RunOut(session_id=session.id, running=session.running, speed=session.speed)


@router.post("/event", responses={409: {"model": ErrorOut}})
async def event(body: EventIn) -> EventOut:
    """Inject an event into the current tick. The response carries the re-deliberated snapshot,
    the fact diff the event caused and, if the plan had to change, the reason."""
    sim = store.session(body.session_id).sim
    before = all_facts(sim.head)
    try:
        after = sim.inject(EventType(body.type), body.args)
    except EventError as err:
        raise HTTPException(409, str(err)) from err
    now = all_facts(after)
    return EventOut(
        snapshot=snapshot_out(after),
        diff=FactDiff(added=sorted(now - before), removed=sorted(before - now)),
        replan_reason=after.replan_reason,
    )


@router.post("/reset")
async def reset(body: SessionIn) -> SnapshotOut:
    session = store.session(body.session_id)
    session.running = False
    return snapshot_out(session.sim.reset())


@router.get("/state")
async def state(session_id: str) -> SnapshotOut:
    return snapshot_out(store.session(session_id).sim.head)


@router.get("/replay/{tick}")
async def replay_tick(tick: int, session_id: str, fresh: bool = False) -> SnapshotOut:
    """Time travel. By default the stored snapshot; ``fresh=true`` rebuilds it from nothing but
    the scenario, seed and event log, which must give the same answer."""
    sim = store.session(session_id).sim
    if not 0 <= tick <= sim.head.tick:
        raise HTTPException(404, f"tick {tick} is outside 0..{sim.head.tick}")
    if fresh:
        return snapshot_out(replay(sim.scenario, tuple(sim.log), tick)[tick])
    return snapshot_out(sim.history[tick])


def log_entries(history: list[Snapshot]) -> list[LogEntryOut]:
    """The event log: what happened at each tick and why the plan changed, straight from the
    traces the engine produced. Plain moves are left out (one per tick would drown the log)."""
    out: list[LogEntryOut] = []
    for snap in history:
        t = snap.tick
        for e in snap.trace:
            if isinstance(e, EventApplied):
                out.append(LogEntryOut(tick=t, kind="event", text=f"{e.event_type} {e.args}"))
            elif isinstance(e, EventRejected):
                text = f"{e.event_type} {e.args} refused"
                out.append(LogEntryOut(tick=t, kind="rejected", text=text, reason=e.reason))
            elif isinstance(e, FireSpread):
                out.append(
                    LogEntryOut(
                        tick=t, kind="spread", text=f"fire spread to {len(e.ignited)} cell(s)"
                    )
                )
            elif isinstance(e, PersonStatusChanged):
                text = f"{e.person_id}: {e.old} → {e.new}"
                out.append(LogEntryOut(tick=t, kind="status", text=text))
            elif isinstance(e, ActionExecuted) and e.action in ("PickUp", "DropOff"):
                out.append(LogEntryOut(tick=t, kind="action", text=e.detail))
            elif isinstance(e, PlanInvalidated):
                out.append(
                    LogEntryOut(tick=t, kind="replan", text="plan invalidated", reason=e.reason)
                )
            elif isinstance(e, PlanAdopted):
                text = f"new plan ({e.change}): {' → '.join(e.steps)}  cost {e.cost:g}"
                out.append(LogEntryOut(tick=t, kind="plan", text=text, reason=e.reason))
            elif isinstance(e, NoValidPlan):
                out.append(
                    LogEntryOut(
                        tick=t, kind="stuck", text="no valid plan", reason="; ".join(e.reasons)
                    )
                )
    return out


@router.get("/log")
async def log(session_id: str) -> list[LogEntryOut]:
    return log_entries(store.session(session_id).sim.history)
