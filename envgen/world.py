"""Runtime world — a mutable view over a validated :class:`SceneGraph`.

The scene graph (:mod:`envgen.schema`) is the static description; the World is
what an agent acts on. It holds the player's live position, inventory, and the
set of doors already opened, and answers the spatial queries the renderer and
(later) the navigator/evaluator need.

It intentionally has no notion of *actions* or *rewards* yet — that arrives with
the Gym-like API in build step 6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from envgen.schema import BLOCKING_TYPES, EntityType, SceneGraph, SceneObject

Coord = tuple[int, int]


@dataclass
class World:
    """Live state layered on top of a static :class:`SceneGraph`.

    Its spatial surface (``is_wall`` / ``static_block_at`` / ``passable`` /
    ``neighbors``, all keyed by an ``(x, y)`` :data:`Coord`) deliberately matches
    :class:`envgen.infinite.InfiniteWorld`, so the navigator in
    :mod:`envgen.navigate` runs unchanged on the finite and infinite worlds alike.
    """

    scene: SceneGraph
    player_pos: Coord = (0, 0)
    inventory: set[str] = field(default_factory=set)
    opened: set[str] = field(default_factory=set)  # ids of doors already unlocked

    @classmethod
    def from_scene(cls, scene: SceneGraph) -> World:
        """Build a world, seeding the player position from the scene."""
        player = scene.player
        start = player.pos if player else (0, 0)
        return cls(scene=scene, player_pos=start)

    # -- spatial queries ---------------------------------------------------
    def is_wall(self, pos: Coord) -> bool:
        return self.scene.grid.is_wall(pos[0], pos[1])

    def objects_at(self, pos: Coord) -> list[SceneObject]:
        """Objects whose position is the given cell (excludes the player)."""
        return [
            o
            for o in self.scene.objects
            if o.pos == pos and o.type is not EntityType.PLAYER
        ]

    def static_block_at(self, pos: Coord) -> bool:
        """A statically blocking object (e.g. a Table) on the cell.

        Doors are *not* treated as static blockers: their locked/open state is
        runtime, so the navigator passes locked-door tiles via its ``blocked``
        set (the infinite-world convention, shared with ``InfiniteWorld``).
        """
        return any(
            obj.type in BLOCKING_TYPES and obj.type is not EntityType.DOOR
            for obj in self.objects_at(pos)
        )

    def passable(self, pos: Coord) -> bool:
        """Whether the player could stand on the cell right now."""
        return not self.is_wall(pos) and not self.static_block_at(pos)

    def neighbors(self, pos: Coord) -> Iterator[Coord]:
        """4-connected passable neighbors — the only graph primitive BFS/A* need."""
        x, y = pos
        for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if self.passable(nxt):
                yield nxt
