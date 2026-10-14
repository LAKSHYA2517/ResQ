import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_headless_demo_runs_the_whole_workflow_and_replays_identically() -> None:
    """``make demo``: load, facts, inference, priority, search, plan, execute, replan, outcome."""
    done = subprocess.run(
        [sys.executable, "scripts/demo_headless.py", "--quiet"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    out = done.stdout
    for marker in (
        "Forward chaining",
        "p2: 5×5 + 3×4 − 1×13 = 24",
        "astar+manhattan",
        "iddfs",
        "resolution True",
        "likelihood weighting",
        "exhaustive",
        "(same move: True)",
        "equal to forward: True",
        "USER EVENT NEW_FIRE",
        "INVALID:",
        "Outcome: complete",
        "identical: True",
        "no valid plan: p1: A* found no route",
    ):
        assert marker in out, marker
