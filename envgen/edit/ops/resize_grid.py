"""ResizeGrid — grow or shrink the tile layer to new dimensions.

Self-registering :class:`~envgen.edit.base.EditOp` under the ``"ResizeGrid"`` key.
Resizes ``scene.grid`` to a new ``w`` x ``h``. Cells that exist in both the old and
new grid keep their tile value; newly added cells (when growing) are padded with a
``fill`` tile (default ``1`` = wall). Objects keep their positions; a shrink that
would push an existing object outside the new bounds is rejected with a specific
:class:`~envgen.edit.base.EditError`. Application is pure — the result is built from
``clone_scene(scene)`` so the input is never mutated.

``inverse`` captures the complete pre-state tile layer (via the ``restore_tiles``
field) so undoing a resize both restores the original dimensions *and* any tile data
trimmed away by a shrink.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from envgen.edit.base import EditError, EditOp, clone_scene, register_op
from envgen.schema import Grid, SceneGraph


@register_op
@dataclass
class ResizeGrid(EditOp):
    """Resize the grid to ``w`` x ``h``, padding new cells with ``fill``.

    ``restore_tiles`` is set only on the op returned by :meth:`inverse`; when
    present it is used verbatim as the new tile layer (restoring trimmed data)
    instead of being rebuilt from the pre-state plus ``fill``.
    """

    op = "ResizeGrid"

    w: int
    h: int
    fill: int = 1
    restore_tiles: list[list[int]] | None = None

    def apply(self, scene: SceneGraph) -> SceneGraph:
        if self.w <= 0 or self.h <= 0:
            raise EditError(
                f"ResizeGrid: dimensions must be positive, got w={self.w} h={self.h}"
            )
        if self.fill not in (0, 1):
            raise EditError(
                f"ResizeGrid: fill must be 0 (floor) or 1 (wall), got {self.fill!r}"
            )

        result = clone_scene(scene)

        for obj in result.objects:
            ox, oy = obj.pos
            if not (0 <= ox < self.w and 0 <= oy < self.h):
                raise EditError(
                    f"ResizeGrid: resizing to {self.w}x{self.h} would orphan object "
                    f"{obj.id!r} at {obj.pos} (out of new bounds)"
                )

        if self.restore_tiles is not None:
            if len(self.restore_tiles) != self.h or any(
                len(row) != self.w for row in self.restore_tiles
            ):
                raise EditError(
                    f"ResizeGrid: restore_tiles shape does not match {self.w}x{self.h}"
                )
            tiles = [list(row) for row in self.restore_tiles]
        else:
            old = result.grid
            tiles = [
                [
                    old.tiles[y][x] if y < old.h and x < old.w else self.fill
                    for x in range(self.w)
                ]
                for y in range(self.h)
            ]

        result.grid = Grid(w=self.w, h=self.h, tiles=tiles)
        return result

    def inverse(self, scene: SceneGraph) -> "ResizeGrid":
        old = scene.grid
        return ResizeGrid(
            w=old.w,
            h=old.h,
            fill=self.fill,
            restore_tiles=[list(row) for row in old.tiles],
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "op": self.op,
            "w": self.w,
            "h": self.h,
            "fill": self.fill,
        }
        if self.restore_tiles is not None:
            out["restore_tiles"] = [list(row) for row in self.restore_tiles]
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResizeGrid":
        for key in ("w", "h"):
            if key not in data:
                raise EditError(f"ResizeGrid: missing required field {key!r}: {data!r}")
        restore = data.get("restore_tiles")
        if restore is not None:
            restore = [[int(v) for v in row] for row in restore]
        return cls(
            w=int(data["w"]),
            h=int(data["h"]),
            fill=int(data.get("fill", 1)),
            restore_tiles=restore,
        )
