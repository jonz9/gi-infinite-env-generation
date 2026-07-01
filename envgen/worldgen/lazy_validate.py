"""Lazy solvability validation across chunks (Stage 4, ticket S4-T14).

The infinite analogue of :func:`envgen.navigate.validate_solvable`: it proves the
macro layout's puzzle solvable on an *unbounded* world by running the same
key-before-door + exit-reachability checks over :meth:`InfiniteWorld.neighbors`, but
(a) with hazard tiles blocked (routes must avoid Lava/Water) and (b) bounded by
``max_expansions`` so the search stays on the task-relevant frontier — you never
flood-fill infinity. Returns ``(ok, msg)``; the message feeds a repair loop.
"""
from __future__ import annotations

from envgen.infinite import InfiniteWorld
from envgen.navigate import lazy_bfs
from envgen.schema import EntityType, SceneObject
from envgen.worldgen.hazards import safe_neighbors


def _one(objs: list[SceneObject], t: EntityType) -> SceneObject | None:
    return next((o for o in objs if o.type is t), None)


def _all(objs: list[SceneObject], t: EntityType) -> list[SceneObject]:
    return [o for o in objs if o.type is t]


def lazy_validate(
    world: InfiniteWorld, *, max_expansions: int = 100_000
) -> tuple[bool, str]:
    """Prove the world's macro objects solvable, hazard-aware and bounded.

    - key-before-door: each Key reachable with all locked-Door tiles blocked.
    - reachability: the Exit reachable once doors open.
    Hazardous cells are removed from the graph; hitting ``max_expansions`` reports
    the target unreachable (the world is too large / the route too long to prove).
    """
    objects = world.layout.objects()
    player = _one(objects, EntityType.PLAYER)
    if player is None:
        return False, "no Player object"
    exit_ = _one(objects, EntityType.EXIT)
    if exit_ is None:
        return False, "no Exit object"

    nb = safe_neighbors(world)
    door_tiles = frozenset(o.pos for o in _all(objects, EntityType.DOOR) if o.locked)

    for key in _all(objects, EntityType.KEY):
        pre = lazy_bfs(
            player.pos, lambda p, k=key.pos: p == k, nb,
            blocked=door_tiles, max_expansions=max_expansions,
        )
        if not pre.reachable:
            return False, f"key '{key.id}' is unreachable before its door opens"

    final = lazy_bfs(
        player.pos, lambda p, e=exit_.pos: p == e, nb, max_expansions=max_expansions
    )
    if not final.reachable:
        return False, "exit is unreachable"
    return True, "ok"
