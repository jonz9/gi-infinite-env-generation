"""Unit tests for the runtime world + ASCII renderer (build step 2)."""

from pathlib import Path

from envgen.render import render
from envgen.schema import SceneGraph
from envgen.world import World

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "room_key_door.json"


def _world() -> World:
    return World.from_scene(SceneGraph.from_json(EXAMPLE.read_text()))


def test_world_seeds_player_position() -> None:
    assert _world().player_pos == (1, 1)


def test_passable_rules() -> None:
    w = _world()
    assert w.passable((1, 1)) is True  # floor (player start)
    assert w.passable((0, 0)) is False  # border wall
    assert w.passable((2, 2)) is False  # table is a static blocker
    # Infinite-world convention: doors are never static blockers. Locked-door
    # gating is the navigator's job via its `blocked` set, not `passable`.
    assert w.passable((6, 3)) is True


def test_neighbors_are_passable() -> None:
    w = _world()
    nbrs = set(w.neighbors((1, 1)))
    assert (2, 1) in nbrs and (1, 2) in nbrs  # open floor
    assert (0, 1) not in nbrs and (1, 0) not in nbrs  # border walls


def test_render_shape_and_glyphs() -> None:
    out = render(_world())
    rows = out.splitlines()
    assert len(rows) == 8 and all(len(r) == 12 for r in rows)
    assert out.count("@") == 1
    assert out.count("T") == 2
    assert "k" in out and "E" in out and "D" in out


def test_door_glyph_reflects_state() -> None:
    w = _world()
    assert "D" in render(w) and "d" not in render(w)
    w.opened.add("door1")
    assert "d" in render(w)


def test_player_glyph_overrides_object_cell() -> None:
    w = _world()
    w.player_pos = (4, 6)  # stand on the key cell
    assert render(w).splitlines()[6][4] == "@"
