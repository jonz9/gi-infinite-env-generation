"""Lazy BFS over a (possibly infinite) world — navigator + solvability validator.

FORWARD-LOOKING SKETCH for build steps 4 (validator) and 7 (solver). The hard part of
"infinite + code-level-verifiable": you cannot flood-fill an infinite grid. Resolution
(transferred from InfiniteDiffusion's lazy sampling): tasks are *bounded*, so BFS only
materializes the chunks on its frontier and is capped to the task-relevant subgraph.
:class:`~envgen.infinite.InfiniteWorld`'s LRU cache evicts explored chunks, so memory
stays bounded. The validator never needs the whole world — only the reachable frontier.

The functions here take a ``neighbors`` callable, so they run unchanged on the finite
``world.World`` and the infinite ``infinite.InfiniteWorld`` alike.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from envgen.schema import EntityType, SceneObject

Coord = tuple[int, int]
Neighbors = Callable[[Coord], Iterable[Coord]]
Goal = Callable[[Coord], bool]


@dataclass(frozen=True)
class SearchResult:
    reachable: bool
    path: list[Coord]    # start..goal inclusive; empty if unreachable
    expanded: int        # tiles popped — the lazy-validation budget actually spent


def lazy_bfs(
    start: Coord,
    is_goal: Goal,
    neighbors: Neighbors,
    *,
    blocked: frozenset[Coord] = frozenset(),
    max_expansions: int = 100_000,
) -> SearchResult:
    """BFS over a lazily materialized (possibly infinite) chunk grid.

    ``blocked`` removes tiles from the graph (e.g. locked-door tiles for the
    key-before-door pre-graph). ``max_expansions`` bounds an infinite world to the
    task-relevant subgraph: hit it and the target is reported unreachable.
    """
    frontier: deque[Coord] = deque([start])
    came_from: dict[Coord, Optional[Coord]] = {start: None}
    expanded = 0
    while frontier and expanded < max_expansions:
        cur = frontier.popleft()
        expanded += 1
        if is_goal(cur):
            return SearchResult(True, _reconstruct(came_from, cur), expanded)
        for nxt in neighbors(cur):
            if nxt in blocked or nxt in came_from:
                continue
            came_from[nxt] = cur
            frontier.append(nxt)
    return SearchResult(False, [], expanded)


def _reconstruct(came_from: dict[Coord, Optional[Coord]], node: Coord) -> list[Coord]:
    path: list[Coord] = []
    cursor: Optional[Coord] = node
    while cursor is not None:
        path.append(cursor)
        cursor = came_from[cursor]
    return list(reversed(path))


def _one(objs: list[SceneObject], type_: EntityType) -> Optional[SceneObject]:
    return next((o for o in objs if o.type is type_), None)


def _all(objs: list[SceneObject], type_: EntityType) -> list[SceneObject]:
    return [o for o in objs if o.type is type_]


def validate_solvable(
    neighbors: Neighbors, objects: list[SceneObject]
) -> tuple[bool, str]:
    """Code-level solvability via lazy BFS, on the task-relevant subgraph only.

    - key-before-door: each Key must be reachable with all locked-Door tiles blocked
      (rules out "key locked behind its own door").
    - reachability: the Exit must be reachable once doors are open.

    ``objects`` is the macro layer's semantic object list (finite, LLM-authored). The
    returned message feeds the planner repair loop (build step 5) on failure.
    """
    player = _one(objects, EntityType.PLAYER)
    if player is None:
        return False, "no Player object"
    exit_ = _one(objects, EntityType.EXIT)
    if exit_ is None:
        return False, "no Exit object"

    door_tiles = frozenset(o.pos for o in _all(objects, EntityType.DOOR) if o.locked)

    for key in _all(objects, EntityType.KEY):
        pre = lazy_bfs(player.pos, lambda p, k=key.pos: p == k, neighbors, blocked=door_tiles)
        if not pre.reachable:
            return False, f"key '{key.id}' is unreachable before its door opens"

    final = lazy_bfs(player.pos, lambda p, e=exit_.pos: p == e, neighbors)
    if not final.reachable:
        return False, "exit is unreachable"
    return True, "ok"
