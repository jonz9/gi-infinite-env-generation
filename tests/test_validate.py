"""Tests for the composed validator (build step 4).

Each broken variant is built by loading the worked example and mutating the
dataclasses (``SceneObject`` is a mutable dataclass), so the tests stay anchored
to the real schema rather than hand-rolled fixtures.
"""

from __future__ import annotations

from pathlib import Path

from envgen.schema import SceneGraph
from envgen.validate import ValidationReport, validate

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "room_key_door.json"


def _scene() -> SceneGraph:
    return SceneGraph.from_json(EXAMPLE.read_text())


def test_example_validates_ok() -> None:
    report = validate(_scene())
    assert isinstance(report, ValidationReport)
    assert report.ok is True
    assert report.errors == []


def test_object_on_wall_tile() -> None:
    scene = _scene()
    scene.get("key1").pos = (0, 0)  # (0,0) is a wall in the example border
    report = validate(scene)
    assert report.ok is False
    assert "object 'key1' at (0,0) is on a wall tile" in report.errors


def test_two_tables_overlap() -> None:
    scene = _scene()
    table1 = scene.get("table1")
    scene.get("table2").pos = table1.pos  # both at (2,2)
    report = validate(scene)
    assert report.ok is False
    assert "object 'table2' at (2,2) overlaps 'table1'" in report.errors


def test_duplicate_id_surfaces() -> None:
    scene = _scene()
    scene.get("table2").id = "table1"  # collide ids
    report = validate(scene)
    assert report.ok is False
    assert any("duplicate object id 'table1'" in e for e in report.errors)


def test_key_behind_its_own_locked_door() -> None:
    scene = _scene()
    # Move the key into the right-hand room, reachable only through door1 (locked).
    scene.get("key1").pos = (8, 6)
    report = validate(scene)
    assert report.ok is False
    assert any("key1" in e and "unreachable" in e for e in report.errors)


def test_player_may_stand_on_exit() -> None:
    # Stackability rule: Player + Exit may share a cell (no overlap error).
    scene = _scene()
    scene.get("player").pos = scene.get("exit").pos
    report = validate(scene)
    overlap_errors = [e for e in report.errors if "overlaps" in e]
    assert overlap_errors == []
