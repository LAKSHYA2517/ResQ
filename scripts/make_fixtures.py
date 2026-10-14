"""Regenerate web/src/test/fixtures.json from real engine runs (run after a snapshot schema change):

uv run python scripts/make_fixtures.py
"""

import json
from pathlib import Path

from api.schemas import all_facts, snapshot_out
from resq.agent.loop import Simulation
from resq.world.events import EventType
from resq.world.scenarios import load_all

OUT = Path(__file__).resolve().parents[1] / "web" / "src" / "test" / "fixtures.json"


def main() -> None:
    scenarios = load_all()
    sim = Simulation(scenarios["showcase"])
    first = snapshot_out(sim.head).model_dump(mode="json")
    for _ in range(5):
        sim.step()
    cell = sim.head.route[2]
    before = all_facts(sim.head)
    replanned = sim.inject(EventType.NEW_FIRE, {"pos": list(cell)})
    after = all_facts(replanned)
    stuck = Simulation(scenarios["impossible"]).head
    OUT.write_text(
        json.dumps(
            {
                "first": first,
                "replanned": snapshot_out(replanned).model_dump(mode="json"),
                "stuck": snapshot_out(stuck).model_dump(mode="json"),
                "diff": {"added": sorted(after - before), "removed": sorted(before - after)},
                "fireCell": list(cell),
            },
            indent=1,
        )
    )
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
