"""Objective-aware solver — prove the *typed objective*, not just exit-reachability.

:func:`envgen.solve.solve` proves the legacy goal ("reach exit"). With typed
objectives (:mod:`envgen.objective`) the win condition can require more — e.g.
``has key2 AND reach exit`` where key2 opens nothing on the route. This module plans
for the predicate tree itself: it lowers the objective to DNF alternatives of
``(items to collect, place to stand)``, plans each with the same key-before-door BFS
discipline as the finite solver, **executes** the actions on a fresh
:class:`~envgen.env.GridEnv`, and reports solved only when
:func:`envgen.objective.satisfied` holds on the executed end-state — the objective
predicate is the ground truth, the planner merely proposes.

Legacy scenes (goal maps to ``Reach(<exit>)``) delegate to the proven ``solve()``,
so behavior on everything built so far is unchanged.
"""
from __future__ import annotations

from typing import List, Optional, Set, Tuple

from envgen import navigate
from envgen.env import Action, GridEnv
from envgen.objective import All, Any_, Has, Predicate, Reach, objective_from_scene, satisfied
from envgen.schema import EntityType, SceneGraph, SceneObject
from envgen.solve import SolveResult, solve
from envgen.world import Coord, World

_DELTA_TO_ACTION = {action.delta: action for action in Action}

#: One DNF alternative: the item ids to collect, and the entity ids to stand on.
_Alt = Tuple[frozenset, frozenset]

_MAX_ALTS = 16   # cap Any-branch fan-out so lowering stays bounded


def solve_objective(scene: SceneGraph) -> SolveResult:
    """Plan + execute a rollout that satisfies the scene's typed objective."""
    objective = objective_from_scene(scene)
    if _is_legacy_reach_exit(objective, scene):
        return solve(scene)

    player = scene.player
    if player is None:
        return SolveResult(False, reason="scene has no Player")

    reasons: List[str] = []
    for items, targets in _to_dnf(objective)[:_MAX_ALTS]:
        path, reason = _plan_alt(scene, player.pos, items, targets)
        if path is None:
            reasons.append(reason)
            continue
        actions = _path_to_actions(path)
        done = _execute_and_check(scene, actions)
        if done:
            return SolveResult(True, actions, path,
                               f"objective '{objective.describe()}' met in {len(actions)} actions")
        reasons.append("executed plan did not satisfy the objective")
    detail = "; ".join(reasons) or "no satisfiable alternative"
    return SolveResult(False, reason=f"objective '{objective.describe()}' unmet: {detail}")


def _is_legacy_reach_exit(objective: Predicate, scene: SceneGraph) -> bool:
    """True when the objective is exactly Reach(<an Exit object>) — solve()'s case."""
    if not isinstance(objective, Reach):
        return False
    target = scene.get(objective.target)
    return target is not None and target.type is EntityType.EXIT


# --- predicate tree -> DNF alternatives ----------------------------------------
def _to_dnf(objective: Predicate) -> List[_Alt]:
    """Lower the tree to alternatives of (Has-item ids, Reach-target ids)."""
    if isinstance(objective, Has):
        return [(frozenset({objective.item}), frozenset())]
    if isinstance(objective, Reach):
        return [(frozenset(), frozenset({objective.target}))]
    if isinstance(objective, Any_):
        return [alt for term in objective.terms for alt in _to_dnf(term)][:_MAX_ALTS]
    if isinstance(objective, All):
        alts: List[_Alt] = [(frozenset(), frozenset())]
        for term in objective.terms:
            alts = [(i | ti, t | tt) for i, t in alts for ti, tt in _to_dnf(term)][:_MAX_ALTS]
        return alts
    return []


# --- planning one alternative ---------------------------------------------------
def _plan_alt(
    scene: SceneGraph, start: Coord, items: frozenset, targets: frozenset
) -> Tuple[Optional[List[Coord]], str]:
    """Route: collect every required item, then stand on the (single) target cell."""
    final, reason = _final_pos(scene, targets)
    if reason:
        return None, reason
    for iid in items:
        obj = scene.get(iid)
        if obj is None:
            return None, f"objective names unknown item {iid!r}"
        if obj.type is not EntityType.KEY:
            return None, f"objective item {iid!r} is a {obj.type.value}, not collectible"

    world = World.from_scene(scene)
    locked = {d.id: d for d in scene.of_type(EntityType.DOOR) if d.locked}
    blocked: Set[Coord] = {d.pos for d in locked.values()}
    # stepping on an Exit ends the episode, so route mid-plan legs around exit tiles
    exits: Set[Coord] = {o.pos for o in scene.of_type(EntityType.EXIT)}
    pending = set(items)
    cur, path = start, [start]

    while pending:
        step = _collect_one(scene, world, cur, pending, locked, blocked, exits)
        if step is None:
            return None, f"item(s) {sorted(pending)} unreachable"
        cur, seg = step
        path += seg
    if final is not None:
        res = _bfs(world, cur, final, blocked | (exits - {final}))
        if res is None:
            return None, "objective target unreachable"
        path += res
    return path, ""


def _final_pos(scene: SceneGraph, targets: frozenset) -> Tuple[Optional[Coord], str]:
    """All Reach targets must resolve and share one cell (you stand in one place)."""
    positions = set()
    for tid in targets:
        obj = scene.get(tid)
        if obj is None:
            return None, f"objective names unknown target {tid!r}"
        positions.add(obj.pos)
    if len(positions) > 1:
        return None, f"objective requires standing on {len(positions)} different cells at once"
    return (next(iter(positions)) if positions else None), ""


def _collect_one(scene, world, cur, pending, locked, blocked, exits):
    """Walk to one reachable pending item — or to an unlocking key to make progress.

    Mutates ``pending``/``locked``/``blocked`` on success; BFS legs avoid ``exits``
    (stepping on an Exit would end the episode mid-plan).
    """
    for iid in sorted(pending):
        seg = _bfs(world, cur, scene.get(iid).pos, blocked | exits)
        if seg is not None:
            pending.discard(iid)
            _unblock(scene, iid, locked, blocked)
            return scene.get(iid).pos, seg
    # no required item reachable: open a door via any reachable key (aux subgoal)
    for door_id, door in sorted(locked.items()):
        key = next((k for k in scene.of_type(EntityType.KEY) if k.opens == door_id), None)
        if key is None:
            continue
        seg = _bfs(world, cur, key.pos, blocked | exits)
        if seg is not None:
            del locked[door_id]
            blocked.discard(door.pos)
            pending.discard(key.id)   # collecting it may also satisfy a requirement
            return key.pos, seg
    return None


def _unblock(scene: SceneGraph, key_id: str, locked: dict, blocked: Set[Coord]) -> None:
    """Collecting ``key_id`` makes its door passable for subsequent legs."""
    key = scene.get(key_id)
    if key is not None and key.opens in locked:
        blocked.discard(locked.pop(key.opens).pos)


def _bfs(world: World, src: Coord, goal: Coord, blocked: Set[Coord]) -> Optional[List[Coord]]:
    """Path ``src``->``goal`` minus ``src``, or None. ``src == goal`` is a no-op leg."""
    res = navigate.lazy_bfs(src, lambda p: p == goal, world.neighbors, blocked=frozenset(blocked))
    return res.path[1:] if res.reachable else None


# --- execution (the proof) ------------------------------------------------------
def _path_to_actions(path: List[Coord]) -> List[Action]:
    actions = []
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        action = _DELTA_TO_ACTION.get((x2 - x1, y2 - y1))
        if action is None:
            raise ValueError(f"non-adjacent step {(x1, y1)} -> {(x2, y2)}")
        actions.append(action)
    return actions


def _execute_and_check(scene: SceneGraph, actions: List[Action]) -> bool:
    """Run the actions on a fresh env; the objective predicate judges the end-state."""
    env = GridEnv(scene)
    env.reset()
    for action in actions:
        env.step(action)
    return satisfied(scene, env.world.player_pos, frozenset(env.world.inventory))
