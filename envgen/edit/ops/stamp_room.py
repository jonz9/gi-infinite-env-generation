"""StampRoom — stamp a walled rectangular room onto the tile layer (S1-T12).

Self-registering :class:`~envgen.edit.base.EditOp` under the ``"StampRoom"`` key.
Given an inclusive rectangle ``rect=[x0, y0, x1, y1]`` it sets the border cells to
wall (``1``) and the interior cells to floor (``0``), optionally punching a 1-cell
doorway gap (floor) on a chosen side (``"N"``/``"S"``/``"E"``/``"W"`` or ``None``).

Rejections (specific :class:`~envgen.edit.base.EditError`):

* any rectangle corner out of the grid bounds;
* a rectangle smaller than 3x3 (a walled room needs a non-empty interior).

Application is pure — the result is built from ``clone_scene(scene)`` (which
deep-copies the tile rows) so the input scene is never mutated.

``inverse`` captures the prior tile block covering the rectangle (via the
``restore_tiles`` field) and replays it, so undoing a stamp restores the exact
tiles that were there before — including whatever the stamp overwrote.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from envgen.edit.base import EditError, EditOp, clone_scene, register_op
from envgen.schema import SceneGraph

_WALL = 1
_FLOOR = 0
_SIDES = ("N", "S", "E", "W")


def _as_rect(value: Any) -> tuple[int, int, int, int]:
    """Coerce ``value`` into a normalized ``(x0, y0, x1, y1)`` int tuple or raise."""
    if not (isinstance(value, (list, tuple)) and len(value) == 4):
        raise EditError(f"StampRoom: rect must be [x0, y0, x1, y1], got {value!r}")
    try:
        x0, y0, x1, y1 = (int(v) for v in value)
    except (TypeError, ValueError):
        raise EditError(f"StampRoom: rect must be integer [x0, y0, x1, y1], got {value!r}")
    # Normalize so x0<=x1 and y0<=y1 regardless of corner ordering.
    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0
    return (x0, y0, x1, y1)


@register_op
@dataclass
class StampRoom(EditOp):
    """Stamp a walled room (wall border, floor interior) over ``rect``.

    ``door`` (optional) punches a 1-cell floor doorway on the named side. ``restore_tiles``
    is set only on the op returned by :meth:`inverse`; when present the rectangle is
    overwritten verbatim with it (restoring the prior block) instead of being stamped.
    """

    op = "StampRoom"

    rect: tuple[int, int, int, int]
    door: str | None = None
    restore_tiles: list[list[int]] | None = None

    def _validated_rect(self, scene: SceneGraph) -> tuple[int, int, int, int]:
        x0, y0, x1, y1 = _as_rect(self.rect)
        grid = scene.grid
        for cx, cy in ((x0, y0), (x1, y1)):
            if not grid.in_bounds(cx, cy):
                raise EditError(
                    f"StampRoom: rect [{x0}, {y0}, {x1}, {y1}] is out of bounds "
                    f"for grid {grid.w}x{grid.h}"
                )
        w, h = x1 - x0 + 1, y1 - y0 + 1
        if w < 3 or h < 3:
            raise EditError(
                f"StampRoom: room must be at least 3x3, got {w}x{h} "
                f"from rect [{x0}, {y0}, {x1}, {y1}]"
            )
        return x0, y0, x1, y1

    def _door_cell(self, x0: int, y0: int, x1: int, y1: int) -> tuple[int, int] | None:
        """The single border cell to open as a doorway, or ``None`` if no door."""
        if self.door is None:
            return None
        side = self.door.upper()
        if side not in _SIDES:
            raise EditError(
                f"StampRoom: door must be one of {_SIDES} or None, got {self.door!r}"
            )
        mid_x = (x0 + x1) // 2
        mid_y = (y0 + y1) // 2
        return {
            "N": (mid_x, y0),
            "S": (mid_x, y1),
            "W": (x0, mid_y),
            "E": (x1, mid_y),
        }[side]

    def apply(self, scene: SceneGraph) -> SceneGraph:
        x0, y0, x1, y1 = self._validated_rect(scene)
        result = clone_scene(scene)
        tiles = result.grid.tiles

        if self.restore_tiles is not None:
            expected = (y1 - y0 + 1, x1 - x0 + 1)
            got = (len(self.restore_tiles), len(self.restore_tiles[0]) if self.restore_tiles else 0)
            if got != expected:
                raise EditError(
                    f"StampRoom: restore_tiles shape {got} does not match rect "
                    f"{expected} for [{x0}, {y0}, {x1}, {y1}]"
                )
            for dy, row in enumerate(self.restore_tiles):
                for dx, val in enumerate(row):
                    tiles[y0 + dy][x0 + dx] = val
            return result

        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                border = x in (x0, x1) or y in (y0, y1)
                tiles[y][x] = _WALL if border else _FLOOR

        door = self._door_cell(x0, y0, x1, y1)
        if door is not None:
            tiles[door[1]][door[0]] = _FLOOR
        return result

    def inverse(self, scene: SceneGraph) -> "StampRoom":
        x0, y0, x1, y1 = self._validated_rect(scene)
        tiles = scene.grid.tiles
        block = [
            [tiles[y][x] for x in range(x0, x1 + 1)]
            for y in range(y0, y1 + 1)
        ]
        return StampRoom(rect=(x0, y0, x1, y1), door=None, restore_tiles=block)

    def to_dict(self) -> dict[str, Any]:
        x0, y0, x1, y1 = _as_rect(self.rect)
        out: dict[str, Any] = {"op": self.op, "rect": [x0, y0, x1, y1], "door": self.door}
        if self.restore_tiles is not None:
            out["restore_tiles"] = [list(row) for row in self.restore_tiles]
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StampRoom":
        if "rect" not in data:
            raise EditError(f"StampRoom: missing required field 'rect': {data!r}")
        restore = data.get("restore_tiles")
        if restore is not None:
            restore = [[int(v) for v in row] for row in restore]
        return cls(
            rect=_as_rect(data["rect"]),
            door=data.get("door"),
            restore_tiles=restore,
        )
