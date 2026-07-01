"""Lazy subgoal-chaining solver across chunks (Stage 4, ticket S4-T15).

The infinite analogue of :func:`envgen.solve.solve`: it plans a key-before-door route
(→key →door →exit) over an unbounded :class:`~envgen.infinite.InfiniteWorld` using
:func:`envgen.navigate.lazy_bfs`, hazard-aware and bounded by ``max_expansions``, then
compiles the concatenated tile-path into an :class:`~envgen.env.Action` list.

Unlike the finite solver there is no whole-grid ``GridEnv`` to execute on (the world is
infinite), so ``solved`` is the BFS existence proof itself — the bounded lazy search
*is* the solvability certificate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from envgen.env import Action
from envgen.infinite import Coord, InfiniteWorld
from envgen.navigate import lazy_bfs
from envgen.schema import EntityType, SceneObject
from envgen.worldgen.hazards import safe_neighbors

_DELTA_TO_ACTION = {action.delta: action for action in Action}
_Subgoal = tuple[SceneObject, SceneObject]   # (key, door)


@dataclass
class LazySolveResult:
    """Outcome of :func:`lazy_solve` — a bounded, hazard-aware solvability certificate."""

    solved: bool
    actions: list[Action] = field(default_factory=list)
    path: list[Coord] = field(default_factory=list)
    reason: str = ""
    expanded: int = 0   # total tiles popped — the lazy budget actually spent


def lazy_solve(
    world: InfiniteWorld, *, max_expansions: int = 100_000
) -> LazySolveResult:
    """Plan + compile a solving route over the infinite world, or report why not."""
    objects = world.layout.objects()
    player = next((o for o in objects if o.type is EntityType.PLAYER), None)
    exits = [o for o in objects if o.type is EntityType.EXIT]
    if player is None:
        return LazySolveResult(False, reason="layout has no Player")
    if not exits:
        return LazySolveResult(False, reason="layout has no Exit")

    nb = safe_neighbors(world)
    budget = _Budget(max_expansions)

    order, reason = _plan(nb, budget, player.pos, exits[0].pos, objects)
    if order is None:
        return LazySolveResult(False, path=[player.pos], reason=reason,
                               expanded=budget.spent)
    path, reason = _build_path(nb, budget, player.pos, exits[0].pos, order, objects)
    if path is None:
        return LazySolveResult(False, path=[player.pos], reason=reason,
                               expanded=budget.spent)

    actions = _path_to_actions(path)
    return LazySolveResult(
        True, actions, path,
        f"reached exit in {len(actions)} actions", budget.spent,
    )


class _Budget:
    """Per-search ``max_expansions`` cap (à la :func:`lazy_bfs`), tracking total spent.

    Each subgoal probe gets the full cap — an unreachable-exit probe on an open
    infinite plane must not starve the later key probe of budget — so the whole solve
    is bounded by ``(#doors + 1) * max_expansions``. ``spent`` is cumulative, for the
    result's reported budget.
    """

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.spent = 0

    def bfs(self, nb, src: Coord, goal: Coord, blocked: frozenset[Coord]):
        res = lazy_bfs(src, lambda p: p == goal, nb, blocked=blocked,
                       max_expansions=self.cap)
        self.spent += res.expanded
        return res


def _locked_doors(objects: list[SceneObject]) -> dict[str, SceneObject]:
    return {d.id: d for d in objects if d.type is EntityType.DOOR and d.locked}


def _key_for(door_id: str, objects: list[SceneObject]) -> SceneObject | None:
    return next(
        (k for k in objects if k.type is EntityType.KEY and k.opens == door_id), None
    )


def _plan(nb, budget: _Budget, start: Coord, exit_pos: Coord,
          objects: list[SceneObject]) -> tuple[list[_Subgoal] | None, str]:
    """Greedily order door-openings until the Exit is reachable (or fail)."""
    locked = _locked_doors(objects)
    blocked = {d.pos for d in locked.values()}
    order: list[_Subgoal] = []
    while not budget.bfs(nb, start, exit_pos, frozenset(blocked)).reachable:
        opened = _open_one(nb, budget, start, locked, blocked, objects)
        if opened is None:
            still = ", ".join(sorted(locked)) or "none"
            return None, f"unsolvable: exit unreachable, no key reachable (locked: {still})"
        order.append(opened)
    return order, "ok"


def _open_one(nb, budget: _Budget, start: Coord, locked: dict, blocked: set,
              objects: list[SceneObject]) -> _Subgoal | None:
    for door_id, door in list(locked.items()):
        key = _key_for(door_id, objects)
        if key is None:
            continue
        if budget.bfs(nb, start, key.pos, frozenset(blocked)).reachable:
            del locked[door_id]
            blocked.discard(door.pos)
            return key, door
    return None


def _build_path(nb, budget: _Budget, start: Coord, exit_pos: Coord,
                order: list[_Subgoal], objects: list[SceneObject]
                ) -> tuple[list[Coord] | None, str]:
    blocked = {d.pos for d in objects if d.type is EntityType.DOOR and d.locked}
    current = start
    path: list[Coord] = [current]
    for key, door in order:
        seg = budget.bfs(nb, current, key.pos, frozenset(blocked))
        if not seg.reachable:
            return None, f"no path to key '{key.id}'"
        path += seg.path[1:]
        current = key.pos
        blocked.discard(door.pos)
        seg = budget.bfs(nb, current, door.pos, frozenset(blocked))
        if not seg.reachable:
            return None, f"no path to door '{door.id}'"
        path += seg.path[1:]
        current = door.pos
    seg = budget.bfs(nb, current, exit_pos, frozenset(blocked))
    if not seg.reachable:
        return None, "no path to exit after opening doors"
    return path + seg.path[1:], "ok"


def _path_to_actions(path: list[Coord]) -> list[Action]:
    actions: list[Action] = []
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        action = _DELTA_TO_ACTION.get((x2 - x1, y2 - y1))
        if action is None:
            raise ValueError(f"non-adjacent step {(x1, y1)} -> {(x2, y2)}")
        actions.append(action)
    return actions
