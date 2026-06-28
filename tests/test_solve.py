"""Tests for the solver agent (build step 7).

Proves the solver does not merely find a path but *executes* it on a fresh env
and reaches the Exit (``done``). Also proves it reports a clean, reasoned failure
on an unsolvable scene without the env ever reporting ``done``.
"""

from __future__ import annotations

from pathlib import Path

from envgen.env import Action, GridEnv
from envgen.schema import EntityType, SceneGraph
from envgen.solve import SolveResult, solve

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "room_key_door.json"


def _scene() -> SceneGraph:
    return SceneGraph.from_json(EXAMPLE.read_text())


def _replay(scene: SceneGraph, actions: list[Action]) -> tuple[bool, tuple[int, int]]:
    """Independently replay actions on a fresh env; return (done, final_pos)."""
    env = GridEnv(scene)
    env.reset()
    for action in actions:
        _obs, _reward, done, _info = env.step(action)
        if done:
            break
    return env.done, env.world.player_pos


def test_example_is_solved_and_executes_to_exit() -> None:
    scene = _scene()
    result = solve(scene)
    assert isinstance(result, SolveResult)
    assert result.solved is True
    assert result.actions, "solver should have produced actions"
    assert result.reason

    exit_pos = scene.of_type(EntityType.EXIT)[0].pos
    # Independently re-execute the recorded actions: env must actually reach done.
    done, final_pos = _replay(scene, result.actions)
    assert done is True
    assert final_pos == exit_pos
    # Recorded tile path is consistent with the goal cell.
    assert result.path[0] == scene.player.pos
    assert result.path[-1] == exit_pos


def test_key_behind_its_own_door_is_unsolvable() -> None:
    scene = _scene()
    key = scene.get("key1")
    assert key is not None
    key.pos = (9, 6)  # move the key into the room gated by its own locked door

    result = solve(scene)
    assert result.solved is False
    assert result.reason  # non-empty explanation for the repair loop / report
    assert result.actions == []

    # The env must never report done for the (empty) executed action sequence.
    done, _final = _replay(scene, result.actions)
    assert done is False


def test_walled_off_exit_is_unsolvable() -> None:
    scene = _scene()
    # Wall off the exit cell's only neighbours so it is unreachable.
    for x, y in ((10, 5), (9, 6), (10, 7), (11, 6)):
        if scene.grid.in_bounds(x, y):
            scene.grid.tiles[y][x] = 1
    result = solve(scene)
    assert result.solved is False
    assert result.reason
    done, _final = _replay(scene, result.actions)
    assert done is False
