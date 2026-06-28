"""Tests for the Gym-like environment (build step 6)."""

from __future__ import annotations

from pathlib import Path

from envgen.env import Action, GridEnv, REACH_EXIT_REWARD
from envgen.schema import EntityType, Grid, SceneGraph, SceneObject

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "room_key_door.json"


def _example_env() -> GridEnv:
    return GridEnv(SceneGraph.from_json(EXAMPLE.read_text()))


def _floor(w: int, h: int) -> Grid:
    """An all-floor grid surrounded by nothing (open box)."""
    return Grid(w=w, h=h, tiles=[[0] * w for _ in range(h)])


def test_reset_places_player_at_start() -> None:
    env = _example_env()
    obs = env.reset()
    assert obs["player_pos"] == (1, 1)
    assert obs["inventory"] == frozenset()
    assert obs["done"] is False


def test_bumping_wall_is_noop() -> None:
    env = _example_env()
    env.reset()  # player at (1, 1); (1, 0) and (0, 1) are border walls
    obs, reward, done, info = env.step(Action.UP)
    assert obs["player_pos"] == (1, 1)
    assert done is False
    assert info["event"] == "blocked"
    assert reward < 0  # blocked move still costs a step


def test_table_blocks_move() -> None:
    env = _example_env()
    env.reset()  # tables at (2, 2) and (3, 2)
    env.step(Action.DOWN)  # (1, 1) -> (1, 2)
    obs, _, done, info = env.step(Action.RIGHT)  # toward table at (2, 2)
    assert obs["player_pos"] == (1, 2)
    assert info["event"] == "blocked"
    assert done is False


def _locked_door_scene() -> SceneGraph:
    """3x1 corridor: player | door(locked) | exit, with a key on the player cell."""
    grid = _floor(4, 1)
    objects = [
        SceneObject(id="player", type=EntityType.PLAYER, pos=(0, 0)),
        SceneObject(id="key1", type=EntityType.KEY, pos=(1, 0), opens="door1"),
        SceneObject(id="door1", type=EntityType.DOOR, pos=(2, 0), locked=True),
        SceneObject(id="exit", type=EntityType.EXIT, pos=(3, 0)),
    ]
    return SceneGraph(grid=grid, objects=objects)


def test_locked_door_blocks_without_key() -> None:
    # Same layout but the key sits off-path so the player reaches the door keyless.
    grid = _floor(3, 1)
    scene = SceneGraph(
        grid=grid,
        objects=[
            SceneObject(id="player", type=EntityType.PLAYER, pos=(0, 0)),
            SceneObject(id="door1", type=EntityType.DOOR, pos=(1, 0), locked=True),
            SceneObject(id="exit", type=EntityType.EXIT, pos=(2, 0)),
        ],
    )
    env = GridEnv(scene)
    env.reset()
    obs, _, done, info = env.step(Action.RIGHT)  # into the locked door, no key
    assert obs["player_pos"] == (0, 0)
    assert info["event"] == "blocked"
    assert done is False


def test_key_then_door_passable() -> None:
    env = GridEnv(_locked_door_scene())
    env.reset()
    obs, _, _, info = env.step(Action.RIGHT)  # onto key at (1, 0)
    assert obs["player_pos"] == (1, 0)
    assert info["event"] == "picked_up_key"
    assert obs["inventory"] == frozenset({"key1"})

    obs, _, _, info = env.step(Action.RIGHT)  # onto now-unlockable door at (2, 0)
    assert obs["player_pos"] == (2, 0)
    assert info["event"] == "opened_door"
    assert "door1" in env.world.opened

    obs, reward, done, info = env.step(Action.RIGHT)  # onto exit
    assert obs["player_pos"] == (3, 0)
    assert info["event"] == "reached_exit"
    assert done is True
    assert reward == REACH_EXIT_REWARD


# Hand-authored solution for examples/room_key_door.json:
#   start (1,1) -> key (4,6) -> door (6,3) -> exit (10,6).
_EXAMPLE_SOLUTION = [
    Action.DOWN, Action.DOWN, Action.DOWN, Action.DOWN, Action.DOWN,  # (1,1)->(1,6)
    Action.RIGHT, Action.RIGHT, Action.RIGHT,                          # (1,6)->key(4,6)
    Action.RIGHT,                                                      # ->(5,6)
    Action.UP, Action.UP, Action.UP,                                   # (5,6)->(5,3)
    Action.RIGHT,                                                      # ->door(6,3)
    Action.RIGHT,                                                      # ->(7,3)
    Action.DOWN, Action.DOWN, Action.DOWN,                             # (7,3)->(7,6)
    Action.RIGHT, Action.RIGHT, Action.RIGHT,                          # (7,6)->exit(10,6)
]


def test_full_solution_reaches_exit() -> None:
    env = _example_env()
    env.reset()
    done = False
    total = 0.0
    info = {}
    for action in _EXAMPLE_SOLUTION:
        obs, reward, done, info = env.step(action)
        total += reward
        if done:
            break
    assert done is True
    assert info["event"] == "reached_exit"
    assert obs["player_pos"] == (10, 6)
    assert "key1" in env.world.inventory
    assert "door1" in env.world.opened
    assert total > 0  # +1 exit dominates the small per-step costs
