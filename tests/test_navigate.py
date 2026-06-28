"""Tests for the shared lazy-BFS navigator + solvability validator.

Covers both the finite world (build steps 4/7) and the infinite world, proving
the *same* ``navigate.lazy_bfs`` runs on either — the point of unifying on the
infinite-world spatial convention.
"""

from __future__ import annotations

from pathlib import Path

from envgen import navigate
from envgen.infinite import CHUNK, Chunk, InfiniteWorld, MacroCell, MacroLayout
from envgen.schema import Grid, SceneGraph
from envgen.world import World

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "room_key_door.json"


def _scene() -> SceneGraph:
    return SceneGraph.from_json(EXAMPLE.read_text())


# --- finite world ---------------------------------------------------------
def test_validate_solvable_on_example() -> None:
    sc = _scene()
    ok, msg = navigate.validate_solvable(World.from_scene(sc).neighbors, sc.objects)
    assert ok is True and msg == "ok"


def test_validate_detects_key_behind_its_own_door() -> None:
    sc = _scene()
    key = sc.get("key1")
    assert key is not None
    key.pos = (9, 6)  # move the key into the room its own door gates -> unsolvable
    ok, msg = navigate.validate_solvable(World.from_scene(sc).neighbors, sc.objects)
    assert ok is False and "key1" in msg


def test_lazy_bfs_finds_path_to_exit() -> None:
    sc = _scene()
    w = World.from_scene(sc)
    exit_ = sc.get("exit")
    assert exit_ is not None
    res = navigate.lazy_bfs((1, 1), lambda p: p == exit_.pos, w.neighbors)
    assert res.reachable
    assert res.path[0] == (1, 1) and res.path[-1] == exit_.pos


# --- infinite world (same navigator) --------------------------------------
def _all_floor_chunk(seed: int, cc, cell: MacroCell | None) -> Chunk:
    tiles = [[0] * CHUNK for _ in range(CHUNK)]
    objects = cell.objects if cell else ()
    return Chunk(cc=cc, grid=Grid(w=CHUNK, h=CHUNK, tiles=tiles), objects=objects)


def test_navigator_runs_on_infinite_world() -> None:
    world = InfiniteWorld(MacroLayout(seed=7), _all_floor_chunk)
    # A goal many chunks away: proves lazy, unbounded navigation over the same API.
    res = navigate.lazy_bfs((0, 0), lambda p: p == (40, 40), world.neighbors)
    assert res.reachable and res.path[-1] == (40, 40)


def test_infinite_max_expansions_bounds_search() -> None:
    world = InfiniteWorld(MacroLayout(seed=7), _all_floor_chunk)
    # Unreachable goal in an infinite floor: the budget must stop the search.
    res = navigate.lazy_bfs(
        (0, 0), lambda p: False, world.neighbors, max_expansions=500
    )
    assert res.reachable is False and res.expanded <= 500
