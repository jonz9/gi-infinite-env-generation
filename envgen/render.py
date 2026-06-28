"""ASCII renderer — turn a :class:`World` (or :class:`SceneGraph`) into text.

Deliberately the first renderer: zero dependencies, instantly inspectable, and
enough to prove the whole text->scene->render path. PyGame sprites can replace it
later without touching the schema or the world.

Legend::

    #  wall      .  floor     @  player
    T  table     k  key       E  exit
    D  locked door            d  open door
"""

from __future__ import annotations

import sys

from envgen.schema import EntityType, SceneGraph
from envgen.world import World

#: Object glyphs painted on top of the tile layer.
_GLYPHS: dict[EntityType, str] = {
    EntityType.PLAYER: "@",
    EntityType.TABLE: "T",
    EntityType.KEY: "k",
    EntityType.EXIT: "E",
}

_FLOOR = "."
_WALL = "#"
_DOOR_LOCKED = "D"
_DOOR_OPEN = "d"


def render(world: World) -> str:
    """Render a world to a multi-line ASCII string.

    Object glyphs overwrite tiles; the live player position overwrites whatever
    object glyph would otherwise sit there. When two objects share a cell the
    last one in the object list wins (deterministic, matches JSON order).
    """
    grid = world.scene.grid
    canvas = [
        [_WALL if grid.is_wall(x, y) else _FLOOR for x in range(grid.w)]
        for y in range(grid.h)
    ]

    for obj in world.scene.objects:
        x, y = obj.pos
        if not grid.in_bounds(x, y):
            continue
        if obj.type is EntityType.PLAYER:
            continue  # drawn from live position below
        if obj.type is EntityType.DOOR:
            walkable = (not obj.locked) or obj.id in world.opened
            canvas[y][x] = _DOOR_OPEN if walkable else _DOOR_LOCKED
        else:
            canvas[y][x] = _GLYPHS.get(obj.type, "?")

    px, py = world.player_pos
    if grid.in_bounds(px, py):
        canvas[py][px] = _GLYPHS[EntityType.PLAYER]

    return "\n".join("".join(row) for row in canvas)


def render_scene(scene: SceneGraph) -> str:
    """Convenience: render a static scene at its initial state."""
    return render(World.from_scene(scene))


def _main(argv: list[str]) -> int:
    """``python -m envgen.render <scene.json>``"""
    if len(argv) != 1:
        print("usage: python -m envgen.render <scene.json>")
        return 2
    with open(argv[0], encoding="utf-8") as fh:
        scene = SceneGraph.from_json(fh.read())
    print(f"goal: {scene.goal}\n")
    print(render_scene(scene))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
