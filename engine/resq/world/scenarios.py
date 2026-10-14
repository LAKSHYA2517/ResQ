"""Scenario model, JSON (de)serialisation and validation.

``parse_scenario`` never raises on bad input: it returns every human-readable issue it can find
(with cell positions where relevant) so the builder can highlight them.
"""

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from .events import Event, EventType, arg_errors, parse_pos
from .grid import Cell, in_bounds
from .state import Agent, Exit, Person, State
from .terrain import CHAR_TO_TERRAIN, CostModel, Terrain

# ponytail: assumes the repo layout (editable install, local demo only); pass a dir to load_all
# if the package is ever installed elsewhere.
SCENARIOS_DIR = Path(__file__).resolve().parents[3] / "scenarios"

MIN_SIDE, MAX_SIDE = 5, 30
FIRE_MODES = ("stochastic", "adversarial")
PARAM_KEYS = {
    "p_spread",
    "weights",
    "cost_model",
    "sensor_noise",
    "fire_mode",
    "adversary_depth",
    "adversary_k",
}


@dataclass(frozen=True)
class Weights:
    """Priority(P) = w_r*Risk + w_u*Urgency - w_d*PathCost. Simulation values, not medical."""

    w_r: float = 5.0
    w_u: float = 3.0
    w_d: float = 1.0
    gamma: float = 0.1  # urgency gained per tick spent waiting
    urgency_cap: float = 5.0
    urgent_threshold: float = 3.0  # Urgent(P) is asserted when urgency reaches this
    delta: float = 2.0  # hysteresis margin: switch target only if better by more than this


@dataclass(frozen=True)
class Params:
    p_spread: float = 0.0
    weights: Weights = field(default_factory=Weights)
    cost_model: CostModel = field(default_factory=CostModel)
    sensor_noise: float = 0.0  # chance that a simulated sensor reading is flipped
    fire_mode: str = "stochastic"  # or "adversarial": the fire plays its worst case
    adversary_depth: int = 3  # plies the adversarial fire looks ahead
    adversary_k: int = 1  # cells it may ignite per tick


@dataclass(frozen=True)
class Scenario:
    name: str
    rows: int
    cols: int
    terrain: tuple[str, ...]  # rows of '.', 'r', '#'
    agent: Cell
    people: tuple[Person, ...]
    fire: frozenset[Cell]
    exits: tuple[Exit, ...]
    scripted_events: tuple[Event, ...] = ()
    seed: int = 0
    params: Params = field(default_factory=Params)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "grid_size": [self.rows, self.cols],
            "terrain": list(self.terrain),
            "agent": list(self.agent),
            "people": [
                {"id": p.id, "pos": list(p.pos), "risk": p.risk, "urgency": p.urgency}
                for p in self.people
            ],
            "fire": [list(c) for c in sorted(self.fire)],
            "exits": [
                {"id": e.id, "pos": list(e.pos), "available": e.available} for e in self.exits
            ],
            "scripted_events": [
                {"tick": e.tick, "type": e.type.value, "args": e.args} for e in self.scripted_events
            ],
            "seed": self.seed,
            "params": {
                "p_spread": self.params.p_spread,
                "weights": vars(self.params.weights).copy(),
                "cost_model": vars(self.params.cost_model).copy(),
                "sensor_noise": self.params.sensor_noise,
                "fire_mode": self.params.fire_mode,
                "adversary_depth": self.params.adversary_depth,
                "adversary_k": self.params.adversary_k,
            },
        }


@dataclass(frozen=True)
class Issue:
    message: str
    cell: Cell | None = None
    field: str = ""

    def __str__(self) -> str:
        where = f" at {self.cell}" if self.cell is not None else ""
        return f"{self.field + ': ' if self.field else ''}{self.message}{where}"


class ScenarioError(ValueError):
    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        super().__init__("; ".join(str(i) for i in issues))


def initial_state(scenario: Scenario) -> State:
    terrain = [[CHAR_TO_TERRAIN[ch] for ch in row] for row in scenario.terrain]
    for e in scenario.exits:
        terrain[e.pos[0]][e.pos[1]] = Terrain.EXIT
    return State(
        rows=scenario.rows,
        cols=scenario.cols,
        terrain=tuple(tuple(r) for r in terrain),
        fire=scenario.fire,
        agent=Agent(scenario.agent),
        people=scenario.people,
        exits=scenario.exits,
    )


# --- parsing / validation ---------------------------------------------------------------------


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


class _Parser:
    def __init__(self, rows: int, cols: int) -> None:
        self.rows, self.cols = rows, cols
        self.issues: list[Issue] = []

    def bad(self, message: str, field_: str, cell: Cell | None = None) -> None:
        self.issues.append(Issue(message, cell, field_))

    def cell(self, v: Any, field_: str) -> Cell | None:
        c = parse_pos(v)
        if c is None:
            self.bad(f"expected [row, col] integers, got {v!r}", field_)
            return None
        if not in_bounds(c, self.rows, self.cols):
            self.bad(f"cell {c} is outside the {self.rows}x{self.cols} grid", field_, c)
            return None
        return c

    def items(self, raw: dict[str, Any], key: str) -> list[Any]:
        v = raw.get(key, [])
        if not isinstance(v, list):
            self.bad("expected a list", key)
            return []
        return v


def parse_scenario(raw: Any) -> tuple[Scenario | None, list[Issue]]:
    if not isinstance(raw, dict):
        return None, [Issue("scenario must be a JSON object")]
    issues: list[Issue] = []
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        issues.append(Issue("a non-empty name is required", field="name"))

    size = raw.get("grid_size")
    if not (
        isinstance(size, list)
        and len(size) == 2
        and all(_is_int(x) and MIN_SIDE <= x <= MAX_SIDE for x in size)
    ):
        issues.append(
            Issue(
                f"grid_size must be [rows, cols] with each side {MIN_SIDE}..{MAX_SIDE}, "
                f"got {size!r}",
                field="grid_size",
            )
        )
        return None, issues
    rows, cols = size
    p = _Parser(rows, cols)
    p.issues.extend(issues)

    walls = _parse_terrain(raw.get("terrain"), p)
    fire = _parse_fire(raw, p, walls)
    agent = _parse_agent(raw, p, walls, fire)
    exits = _parse_exits(raw, p, walls, fire)
    people = _parse_people(raw, p, walls, fire, {e.pos for e in exits})
    events = _parse_events(raw, p, {e.id for e in exits})
    seed = raw.get("seed", 0)
    if not _is_int(seed):
        p.bad(f"seed must be an integer, got {seed!r}", "seed")
    params = _parse_params(raw.get("params", {}), p)

    if p.issues or agent is None:
        return None, p.issues
    terrain = raw.get("terrain") or ["." * cols] * rows
    return (
        Scenario(
            name=str(name).strip(),
            rows=rows,
            cols=cols,
            terrain=tuple(terrain),
            agent=agent,
            people=tuple(people),
            fire=frozenset(fire),
            exits=tuple(exits),
            scripted_events=tuple(events),
            seed=seed,
            params=params,
        ),
        [],
    )


def _parse_terrain(raw: Any, p: _Parser) -> set[Cell]:
    walls: set[Cell] = set()
    if raw is None:
        return walls
    if not (isinstance(raw, list) and all(isinstance(r, str) for r in raw)):
        p.bad("terrain must be a list of strings", "terrain")
        return walls
    if len(raw) != p.rows:
        p.bad(f"terrain has {len(raw)} rows, grid_size says {p.rows}", "terrain")
    for r, row in enumerate(raw[: p.rows]):
        if len(row) != p.cols:
            p.bad(f"terrain row {r} has {len(row)} columns, grid_size says {p.cols}", "terrain")
        for c, ch in enumerate(row[: p.cols]):
            if ch not in CHAR_TO_TERRAIN:
                p.bad(f"unknown terrain character {ch!r} (use '.', 'r', '#')", "terrain", (r, c))
            elif CHAR_TO_TERRAIN[ch] is Terrain.WALL:
                walls.add((r, c))
    return walls


def _parse_fire(raw: dict[str, Any], p: _Parser, walls: set[Cell]) -> set[Cell]:
    fire: set[Cell] = set()
    for i, v in enumerate(p.items(raw, "fire")):
        c = p.cell(v, f"fire[{i}]")
        if c is None:
            continue
        if c in walls:
            p.bad("fire cannot start on a wall", f"fire[{i}]", c)
        else:
            fire.add(c)
    return fire


def _parse_agent(raw: dict[str, Any], p: _Parser, walls: set[Cell], fire: set[Cell]) -> Cell | None:
    if "agent" not in raw:
        p.bad("an agent start cell is required", "agent")
        return None
    c = p.cell(raw["agent"], "agent")
    if c is not None and c in walls:
        p.bad("the agent cannot start on a wall", "agent", c)
    elif c is not None and c in fire:
        p.bad("the agent cannot start on a fire cell", "agent", c)
    return c


def _parse_exits(raw: dict[str, Any], p: _Parser, walls: set[Cell], fire: set[Cell]) -> list[Exit]:
    out: list[Exit] = []
    seen_ids: set[str] = set()
    seen_pos: set[Cell] = set()
    items = p.items(raw, "exits")
    if not items:
        p.bad("at least one exit is required", "exits")
    for i, d in enumerate(items):
        f = f"exits[{i}]"
        if not isinstance(d, dict) or not isinstance(d.get("id"), str) or not d["id"]:
            p.bad("each exit needs a string id and pos", f)
            continue
        if d["id"] in seen_ids:
            p.bad(f"duplicate exit id {d['id']!r}", f)
        seen_ids.add(d["id"])
        c = p.cell(d.get("pos"), f)
        if c is None:
            continue
        if c in walls:
            p.bad(f"exit {d['id']!r} is on a wall", f, c)
        elif c in fire:
            p.bad(f"exit {d['id']!r} starts on a fire cell", f, c)
        elif c in seen_pos:
            p.bad(f"exit {d['id']!r} overlaps another exit", f, c)
        seen_pos.add(c)
        out.append(Exit(d["id"], c, bool(d.get("available", True))))
    return out


def _parse_people(
    raw: dict[str, Any], p: _Parser, walls: set[Cell], fire: set[Cell], exit_cells: set[Cell]
) -> list[Person]:
    out: list[Person] = []
    seen_ids: set[str] = set()
    seen_pos: set[Cell] = set()
    items = p.items(raw, "people")
    if not items:
        p.bad("at least one person is required", "people")
    for i, d in enumerate(items):
        f = f"people[{i}]"
        if not isinstance(d, dict) or not isinstance(d.get("id"), str) or not d["id"]:
            p.bad("each person needs a string id and pos", f)
            continue
        pid = d["id"]
        if pid in seen_ids:
            p.bad(f"duplicate person id {pid!r}", f)
        seen_ids.add(pid)
        for key in ("risk", "urgency"):
            v = d.get(key, 0)
            if not (_is_int(v) and 0 <= v <= 5):
                p.bad(f"{pid!r} {key} must be an integer 0..5, got {v!r}", f)
        c = p.cell(d.get("pos"), f)
        if c is None:
            continue
        if c in walls:
            p.bad(f"person {pid!r} is inside a wall", f, c)
        elif c in fire:
            p.bad(
                f"person {pid!r} starts on a fire cell; fire is impassable so they could never be"
                " reached (fire spread may trap people later, but not at the start)",
                f,
                c,
            )
        elif c in exit_cells:
            p.bad(f"person {pid!r} is standing on an exit", f, c)
        elif c in seen_pos:
            p.bad(f"person {pid!r} overlaps another person", f, c)
        seen_pos.add(c)
        out.append(Person(pid, c, int(d.get("risk", 0)), int(d.get("urgency", 0))))
    return out


def _parse_events(raw: dict[str, Any], p: _Parser, exit_ids: set[str]) -> list[Event]:
    out: list[Event] = []
    for i, d in enumerate(p.items(raw, "scripted_events")):
        f = f"scripted_events[{i}]"
        if not (isinstance(d, dict) and _is_int(d.get("tick")) and d["tick"] >= 0):
            p.bad("each event needs an integer tick >= 0, a type and args", f)
            continue
        try:
            etype = EventType(str(d.get("type")))
        except ValueError:
            p.bad(f"unknown event type {d.get('type')!r}", f)
            continue
        args = d.get("args", {})
        if not isinstance(args, dict):
            p.bad("args must be an object", f)
            continue
        errs = arg_errors(etype, args, p.rows, p.cols, exit_ids)
        for msg in errs:
            p.bad(msg, f)
        if not errs:
            out.append(Event(d["tick"], etype, args))
    return out


def _parse_params(raw: Any, p: _Parser) -> Params:
    if not isinstance(raw, dict):
        p.bad("params must be an object", "params")
        return Params()
    for key in raw.keys() - PARAM_KEYS:
        p.bad(f"unknown params key {key!r}", "params")

    def unit(key: str) -> float:
        v = raw.get(key, 0.0)
        if _is_num(v) and 0 <= v <= 1:
            return float(v)
        p.bad(f"{key} must be a number in [0, 1], got {v!r}", f"params.{key}")
        return 0.0

    def whole(key: str, default: int, lo: int, hi: int) -> int:
        v = raw.get(key, default)
        if _is_int(v) and lo <= v <= hi:
            return int(v)
        p.bad(f"{key} must be an integer {lo}..{hi}, got {v!r}", f"params.{key}")
        return default

    fire_mode = raw.get("fire_mode", "stochastic")
    if fire_mode not in FIRE_MODES:
        p.bad(f"fire_mode must be one of {list(FIRE_MODES)}, got {fire_mode!r}", "params.fire_mode")
        fire_mode = "stochastic"
    weights = Weights(**_numbers(raw.get("weights", {}), Weights, p, "params.weights"))
    costs = CostModel(**_numbers(raw.get("cost_model", {}), CostModel, p, "params.cost_model"))
    if min(costs.floor, costs.rubble, costs.exit) <= 0:
        p.bad("floor, rubble and exit costs must be > 0 (A* needs positive step costs)", "params")
    return Params(
        p_spread=unit("p_spread"),
        weights=weights,
        cost_model=costs,
        sensor_noise=unit("sensor_noise"),
        fire_mode=fire_mode,
        adversary_depth=whole("adversary_depth", 3, 1, 5),
        adversary_k=whole("adversary_k", 1, 1, 2),
    )


def _numbers(raw: Any, cls: type, p: _Parser, field_: str) -> dict[str, float]:
    """Non-negative numeric overrides for a dataclass of floats; bad entries become issues."""
    if not isinstance(raw, dict):
        p.bad("expected an object", field_)
        return {}
    allowed = {f.name for f in fields(cls)}
    out: dict[str, float] = {}
    for key, v in raw.items():
        if key not in allowed:
            p.bad(f"unknown key {key!r}", field_)
        elif not (_is_num(v) and v >= 0):
            p.bad(f"{key} must be a number >= 0, got {v!r}", field_)
        else:
            out[key] = float(v)
    return out


# --- files ----------------------------------------------------------------------------------


def load_scenario(path: Path) -> Scenario:
    scenario, issues = parse_scenario(json.loads(path.read_text()))
    if scenario is None:
        raise ScenarioError(issues)
    return scenario


def load_all(directory: Path = SCENARIOS_DIR) -> dict[str, Scenario]:
    """Every ``*.json`` in the directory keyed by file stem, sorted by stem."""
    return {p.stem: load_scenario(p) for p in sorted(directory.glob("*.json"))}
