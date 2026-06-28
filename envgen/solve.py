"""Solver agent — BFS subgoal chaining that EXECUTES on the env (build step 7).

This is the harness's automated *solvability proof*. It does not merely assert a
path exists: it plans a key-before-door-correct route, compiles it to a sequence
of :class:`~envgen.env.Action`, then drives a fresh :class:`~envgen.env.GridEnv`
one step at a time and reports SOLVED only when the env's own ``done`` flag fires
at the Exit.

Strategy (subgoal chaining)
--------------------------
Using a :class:`~envgen.world.World` for path queries (locked doors are *not*
static blockers there — gating is the navigator's ``blocked``-set job):

1. While the Exit is unreachable with all still-locked door tiles blocked, pick a
   still-locked Door whose Key is reachable in that same blocked graph, queue the
   subgoals ``[->key, ->door]`` and treat that door as openable. If no progress is
   possible, the scene is unsolvable.
2. Append a final ``->Exit`` subgoal.

Each subgoal is a :func:`envgen.navigate.lazy_bfs` query; the tile-paths are
concatenated, then consecutive ``(x, y)`` steps are turned into Actions by matching
their ``(dx, dy)`` delta to :attr:`Action.delta`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from envgen import navigate
from envgen.env import Action, GridEnv
from envgen.schema import EntityType, SceneGraph, SceneObject
from envgen.world import Coord, World

#: Reverse map (dx, dy) -> Action, for compiling a tile path into moves.
_DELTA_TO_ACTION = {action.delta: action for action in Action}

#: A planned subgoal pair: collect ``key`` so ``door`` becomes openable.
_Subgoal = Tuple[SceneObject, SceneObject]


@dataclass
class SolveResult:
    """Outcome of :func:`solve`.

    Attributes
    ----------
    solved: ``True`` iff the executed env reported ``done`` at the Exit.
    actions: The Actions actually stepped on the env (empty when unsolved).
    path: The full tile path (player start .. exit) the actions trace.
    reason: Human-readable explanation, for the SOLVED/FAILED report.
    """

    solved: bool
    actions: List[Action] = field(default_factory=list)
    path: List[Coord] = field(default_factory=list)
    reason: str = ""


def solve(scene: SceneGraph) -> SolveResult:
    """Plan a key-before-door route, execute it on a fresh env, and prove SOLVED.

    Returns a :class:`SolveResult` whose ``solved`` flag is taken from the env's
    own ``done`` flag after stepping the compiled actions — an executed proof, not
    a mere path-existence claim.
    """
    world = World.from_scene(scene)
    player = scene.player
    exits = scene.of_type(EntityType.EXIT)
    if player is None:
        return SolveResult(False, reason="scene has no Player")
    if not exits:
        return SolveResult(False, reason="scene has no Exit")
    exit_pos = exits[0].pos

    order, reason = _plan_subgoals(world, player.pos, exit_pos, scene)
    if order is None:
        return SolveResult(False, path=[player.pos], reason=reason)

    path, reason = _build_path(world, player.pos, exit_pos, order, scene)
    if path is None:
        return SolveResult(False, path=[player.pos], reason=reason)

    actions = _path_to_actions(path)
    done, final_pos = _execute(scene, actions)
    return SolveResult(done, actions, path, _verdict(done, final_pos, exit_pos, actions))


def _plan_subgoals(
    world: World, player_pos: Coord, exit_pos: Coord, scene: SceneGraph
) -> Tuple[Optional[List[_Subgoal]], str]:
    """Greedily order door-openings so the Exit becomes reachable (or fail)."""
    locked = {d.id: d for d in scene.of_type(EntityType.DOOR) if d.locked}
    blocked = {d.pos for d in locked.values()}
    order: List[_Subgoal] = []
    while not _reachable(world, player_pos, exit_pos, blocked):
        opened = _open_one_door(world, player_pos, locked, blocked)
        if opened is None:
            still = ", ".join(sorted(locked)) or "none"
            return None, f"unsolvable: exit unreachable and no key reachable (locked: {still})"
        order.append(opened)
    return order, "ok"


def _open_one_door(
    world: World,
    player_pos: Coord,
    locked: dict,
    blocked: set,
) -> Optional[_Subgoal]:
    """Pick a still-locked door whose key is reachable now; mutate state, return it."""
    for door_id, door in list(locked.items()):
        key = _key_for(door_id, world.scene)
        if key is None:
            continue
        if _reachable(world, player_pos, key.pos, blocked):
            del locked[door_id]
            blocked.discard(door.pos)
            return key, door
    return None


def _build_path(
    world: World,
    player_pos: Coord,
    exit_pos: Coord,
    order: List[_Subgoal],
    scene: SceneGraph,
) -> Tuple[Optional[List[Coord]], str]:
    """Concatenate the per-subgoal BFS tile-paths into one start..exit path."""
    blocked = {d.pos for d in scene.of_type(EntityType.DOOR) if d.locked}
    current = player_pos
    path: List[Coord] = [current]
    for key, door in order:
        current, seg = _walk(world, current, key.pos, blocked)
        if seg is None:
            return None, f"no path to key '{key.id}'"
        path += seg
        blocked.discard(door.pos)  # key now held -> door is openable
        current, seg = _walk(world, current, door.pos, blocked)
        if seg is None:
            return None, f"no path to door '{door.id}'"
        path += seg
    current, seg = _walk(world, current, exit_pos, blocked)
    if seg is None:
        return None, "no path to exit after opening doors"
    return path + seg, "ok"


def _walk(
    world: World, src: Coord, goal: Coord, blocked: set
) -> Tuple[Coord, Optional[List[Coord]]]:
    """BFS ``src``->``goal``; return ``(goal, path_without_src)`` or ``(src, None)``."""
    res = navigate.lazy_bfs(
        src, lambda p: p == goal, world.neighbors, blocked=frozenset(blocked)
    )
    if not res.reachable:
        return src, None
    return goal, res.path[1:]


def _reachable(world: World, src: Coord, goal: Coord, blocked: set) -> bool:
    """Whether ``goal`` is BFS-reachable from ``src`` with ``blocked`` tiles removed."""
    res = navigate.lazy_bfs(
        src, lambda p: p == goal, world.neighbors, blocked=frozenset(blocked)
    )
    return res.reachable


def _key_for(door_id: str, scene: SceneGraph) -> Optional[SceneObject]:
    """The Key whose ``.opens`` matches ``door_id`` (``None`` if absent)."""
    return next(
        (k for k in scene.of_type(EntityType.KEY) if k.opens == door_id), None
    )


def _path_to_actions(path: List[Coord]) -> List[Action]:
    """Compile a tile path into Actions by matching each step's (dx, dy) delta."""
    actions: List[Action] = []
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        delta = (x2 - x1, y2 - y1)
        action = _DELTA_TO_ACTION.get(delta)
        if action is None:
            raise ValueError(f"non-adjacent step {(x1, y1)} -> {(x2, y2)} in path")
        actions.append(action)
    return actions


def _execute(scene: SceneGraph, actions: List[Action]) -> Tuple[bool, Coord]:
    """Step the actions on a fresh env; return ``(done, final_player_pos)``."""
    env = GridEnv(scene)
    env.reset()
    for action in actions:
        _obs, _reward, done, _info = env.step(action)
        if done:
            break
    return env.done, env.world.player_pos


def _verdict(done: bool, final_pos: Coord, exit_pos: Coord, actions: List[Action]) -> str:
    """Build the result ``reason`` string from the executed outcome."""
    if done and final_pos == exit_pos:
        return f"reached exit in {len(actions)} actions"
    if done:
        return f"env done at {final_pos}, not the exit {exit_pos}"
    return f"executed {len(actions)} actions but env never reached the exit"


def _main(argv: List[str]) -> int:
    """``python3 -m envgen.solve <scene.json>`` — render, solve, print verdict."""
    from envgen.render import render_scene

    if len(argv) != 1:
        print("usage: python3 -m envgen.solve <scene.json>")
        return 2
    with open(argv[0], encoding="utf-8") as fh:
        scene = SceneGraph.from_json(fh.read())
    print(f"goal: {scene.goal}\n")
    print(render_scene(scene), "\n")
    result = solve(scene)
    print("SOLVED" if result.solved else "FAILED")
    print(f"reason: {result.reason}")
    print(f"actions: {len(result.actions)}")
    return 0 if result.solved else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
