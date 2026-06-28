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

from envgen.schema import BLOCKING_TYPES, EntityType, SceneGraph, SceneObject


@dataclass
class World:
    """Live state layered on top of a static :class:`SceneGraph`."""

    scene: SceneGraph
    player_pos: tuple[int, int] = (0, 0)
    inventory: set[str] = field(default_factory=set)
    opened: set[str] = field(default_factory=set)  # ids of doors already unlocked

    @classmethod
    def from_scene(cls, scene: SceneGraph) -> World:
        """Build a world, seeding the player position from the scene."""
        player = scene.player
        start = player.pos if player else (0, 0)
        return cls(scene=scene, player_pos=start)

    # -- spatial queries ---------------------------------------------------
    def in_bounds(self, x: int, y: int) -> bool:
        return self.scene.grid.in_bounds(x, y)

    def is_wall(self, x: int, y: int) -> bool:
        return self.scene.grid.is_wall(x, y)

    def objects_at(self, x: int, y: int) -> list[SceneObject]:
        """Objects whose position is the given cell (excludes the player)."""
        return [
            o
            for o in self.scene.objects
            if o.pos == (x, y) and o.type is not EntityType.PLAYER
        ]

    def is_blocked_by_object(self, x: int, y: int) -> bool:
        """True if a blocking object occupies the cell.

        Tables always block. A Door blocks only while it is still locked and has
        not yet been opened (an unlocked or opened door is walkable).
        """
        for obj in self.objects_at(x, y):
            if obj.type not in BLOCKING_TYPES:
                continue
            if obj.type is EntityType.DOOR and (not obj.locked or obj.id in self.opened):
                continue
            return True
        return False

    def passable(self, x: int, y: int) -> bool:
        """Whether the player could stand on the cell right now."""
        return not self.is_wall(x, y) and not self.is_blocked_by_object(x, y)
