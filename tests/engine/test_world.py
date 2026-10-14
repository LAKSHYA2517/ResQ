import json
from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from resq.world.scenarios import (
    Scenario,
    ScenarioError,
    initial_state,
    load_scenario,
    parse_scenario,
)
from resq.world.terrain import CostModel, Terrain

EXPECTED = {
    "basic_rescue",
    "fire_emergency",
    "multiple_people",
    "blocked_exit",
    "dynamic_emergency",
    "spreading_fire",
    "triage_dilemma",
    "impossible",
    "showcase",
    "mass_evacuation",
}


def test_all_predefined_scenarios_ship_and_validate(shipped: dict[str, Scenario]) -> None:
    assert set(shipped) == EXPECTED


def test_scenario_json_round_trips(shipped: dict[str, Scenario]) -> None:
    for scenario in shipped.values():
        again, issues = parse_scenario(json.loads(json.dumps(scenario.to_dict())))
        assert issues == []
        assert again == scenario


def test_exit_cells_become_exit_terrain(make_scenario: Callable[..., Scenario]) -> None:
    state = initial_state(make_scenario())
    assert state.terrain_at((4, 4)) is Terrain.EXIT
    assert state.terrain_at((0, 1)) is Terrain.FLOOR


def test_hot_zone_is_passable_neighbours_of_fire(make_scenario: Callable[..., Scenario]) -> None:
    terrain = [".....", ".....", "..#..", ".....", "....."]
    state = initial_state(make_scenario(terrain=terrain, fire=[[2, 1]]))
    assert state.hot == {(1, 1), (3, 1), (2, 0)}  # (2,2) is a wall: not passable, so not hot
    assert not state.hot & state.fire
    assert state.is_blocked((2, 1)) and state.is_blocked((2, 2))
    assert not state.is_blocked((1, 1))


def test_cost_model_defaults_and_min_step() -> None:
    cm = CostModel()
    assert (cm.floor, cm.rubble, cm.hot_extra) == (1, 3, 4)
    assert cm.terrain_cost(Terrain.WALL) is None
    assert cm.min_step == 1
    assert CostModel(floor=2, rubble=3, exit=5).min_step == 2


# (mutation of the valid base scenario, expected substring, expected cell or None)
BAD: list[tuple[str, dict[str, Any], str, tuple[int, int] | None]] = [
    ("person on fire", {"fire": [[3, 1]]}, "starts on a fire cell", (3, 1)),
    ("agent on fire", {"fire": [[0, 0]]}, "agent cannot start on a fire", (0, 0)),
    ("exit on fire", {"fire": [[4, 4]]}, "exit 'e1' starts on a fire", (4, 4)),
    ("person off grid", {"people": [{"id": "p1", "pos": [9, 9]}]}, "outside the 5x5", (9, 9)),
    ("no people", {"people": []}, "at least one person", None),
    ("no exits", {"exits": []}, "at least one exit", None),
    ("no agent", {"agent": None}, "[row, col]", None),
    ("tiny grid", {"grid_size": [4, 5]}, "5..30", None),
    ("huge grid", {"grid_size": [31, 5]}, "5..30", None),
    (
        "bad char",
        {"terrain": ["x....", ".....", ".....", ".....", "....."]},
        "unknown terrain",
        (0, 0),
    ),
    ("short terrain", {"terrain": ["....."]}, "1 rows", None),
    (
        "person in wall",
        {"terrain": [".....", ".....", ".....", ".#...", "....."]},
        "inside a wall",
        (3, 1),
    ),
    (
        "duplicate person id",
        {"people": [{"id": "p", "pos": [1, 1]}, {"id": "p", "pos": [3, 3]}]},
        "duplicate person id",
        None,
    ),
    (
        "people overlap",
        {"people": [{"id": "a", "pos": [1, 1]}, {"id": "b", "pos": [1, 1]}]},
        "overlaps another person",
        (1, 1),
    ),
    ("person on exit", {"people": [{"id": "a", "pos": [4, 4]}]}, "standing on an exit", (4, 4)),
    (
        "risk out of range",
        {"people": [{"id": "a", "pos": [1, 1], "risk": 9}]},
        "risk must be",
        None,
    ),
    (
        "fire on wall",
        {"terrain": [".....", ".#...", ".....", ".....", "....."], "fire": [[1, 1]]},
        "wall",
        (1, 1),
    ),
    ("bad p_spread", {"params": {"p_spread": 2}}, "p_spread", None),
    ("zero cost", {"params": {"cost_model": {"floor": 0}}}, "must be > 0", None),
    ("unknown param", {"params": {"nope": 1}}, "unknown params key", None),
    ("bad noise", {"params": {"sensor_noise": 1.5}}, "sensor_noise must be", None),
    ("bad fire mode", {"params": {"fire_mode": "angry"}}, "fire_mode must be", None),
    ("bad depth", {"params": {"adversary_depth": 9}}, "adversary_depth must be", None),
    ("bad k", {"params": {"adversary_k": 0}}, "adversary_k must be", None),
    (
        "scripted FIRE_SPREAD",
        {"scripted_events": [{"tick": 1, "type": "FIRE_SPREAD", "args": {}}]},
        "automatic",
        None,
    ),
    (
        "event unknown exit",
        {"scripted_events": [{"tick": 1, "type": "EXIT_BLOCKED", "args": {"exit": "zz"}}]},
        "args.exit",
        None,
    ),
    (
        "event off grid",
        {"scripted_events": [{"tick": 1, "type": "NEW_FIRE", "args": {"pos": [7, 7]}}]},
        "outside the 5x5",
        None,
    ),
]


@pytest.mark.parametrize(("label", "patch", "needle", "cell"), BAD, ids=[b[0] for b in BAD])
def test_validation_reports_human_readable_issue(
    raw: dict[str, Any],
    label: str,
    patch: dict[str, Any],
    needle: str,
    cell: tuple[int, int] | None,
) -> None:
    raw.update(patch)
    scenario, issues = parse_scenario(raw)
    assert scenario is None
    matching = [i for i in issues if needle in i.message]
    assert matching, [str(i) for i in issues]
    if cell is not None:
        assert matching[0].cell == cell
        assert str(cell) in str(matching[0])


def test_validation_collects_several_issues_at_once(raw: dict[str, Any]) -> None:
    raw["fire"] = [[3, 1], [4, 4]]
    _, issues = parse_scenario(raw)
    assert len(issues) == 2


def test_non_object_is_rejected() -> None:
    assert parse_scenario([1, 2])[0] is None


def test_load_scenario_raises_with_issues(tmp_path: Any) -> None:
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"name": "x", "grid_size": [5, 5]}))
    with pytest.raises(ScenarioError) as e:
        load_scenario(f)
    assert e.value.issues


def test_issue_str_without_cell_or_field() -> None:
    from resq.world.scenarios import Issue

    assert str(Issue("boom")) == "boom"


JSON = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(-5, 40)
    | st.floats(allow_nan=False)
    | st.text(max_size=6),
    lambda kids: (
        st.lists(kids, max_size=4) | st.dictionaries(st.text(max_size=6), kids, max_size=4)
    ),
    max_leaves=8,
)
TOP_KEYS = [
    "name",
    "grid_size",
    "terrain",
    "agent",
    "people",
    "fire",
    "exits",
    "scripted_events",
    "seed",
    "params",
]


@settings(max_examples=300, deadline=None)
@given(st.sampled_from(TOP_KEYS), JSON, st.booleans())
def test_prop_parse_never_raises_and_is_consistent(key: str, value: Any, nest: bool) -> None:
    raw: dict[str, Any] = {
        "name": "t",
        "grid_size": [5, 5],
        "agent": [0, 0],
        "people": [{"id": "p1", "pos": [3, 1]}],
        "fire": [],
        "exits": [{"id": "e1", "pos": [4, 4]}],
    }
    raw[key] = [value] if nest and key in ("people", "exits", "fire", "scripted_events") else value
    scenario, issues = parse_scenario(raw)
    assert (scenario is None) == bool(issues)
    for issue in issues:
        str(issue)
    if scenario is not None:
        initial_state(scenario)  # a scenario that parses is always buildable
