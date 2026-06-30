"""FillRegion — fill an axis-aligned rectangle with a tile value (S1-T06).

Self-registering :class:`~envgen.edit.base.EditOp` under the ``"FillRegion"`` key.
Given a rectangle ``[x0, y0, x1, y1]`` (inclusive corners, ``x0<=x1`` and
``y0<=y1``) it sets every tile in that block to ``value`` (``0`` = floor, ``1`` =
wall). Rejected with a specific :class:`~envgen.edit.base.EditError`:

* a rectangle that leaves the grid bounds,
* a degenerate/inverted rectangle (``x0>x1`` or ``y0>y1``),
* filling WALLs (``value=1``) under any existing object — that would trap or bury it.

Application is pure — the result is built from ``clone_scene(scene)`` (which
deep-copies the tile rows) so the input scene is never mutated.

``inverse`` restores the exact prior tile values across the rectangle via a
companion :class:`_RestoreRegion` op (a fill is lossy, so the inverse replays the
captured block rather than re-filling a single value).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from envgen.edit.base import EditError, EditOp, clone_scene, register_op
from envgen.schema import SceneGraph

_TILE_VALUES = (0, 1)


def _as_int(value: Any, name: str) -> int:
    """Coerce ``value`` to an int or raise EditError."""
    try:
        return int(value)
    except (TypeError, ValueError):
        raise EditError(f"FillRegion: {name} must be an integer, got {value!r}")


@register_op
@dataclass
class FillRegion(EditOp):
    """Fill the inclusive rectangle ``[x0, y0, x1, y1]`` with ``value`` (0 or 1)."""

    op = "FillRegion"

    x0: int
    y0: int
    x1: int
    y1: int
    value: int

    def _rect(self) -> tuple[int, int, int, int]:
        return (
            _as_int(self.x0, "x0"),
            _as_int(self.y0, "y0"),
            _as_int(self.x1, "x1"),
            _as_int(self.y1, "y1"),
        )

    def _validate(self, scene: SceneGraph) -> tuple[int, int, int, int, int]:
        x0, y0, x1, y1 = self._rect()
        value = _as_int(self.value, "value")
        if value not in _TILE_VALUES:
            raise EditError(f"FillRegion: value must be 0 or 1, got {value!r}")
        if x0 > x1 or y0 > y1:
            raise EditError(
                f"FillRegion: inverted rectangle [{x0}, {y0}, {x1}, {y1}] "
                "(require x0<=x1 and y0<=y1)"
            )
        grid = scene.grid
        if not (grid.in_bounds(x0, y0) and grid.in_bounds(x1, y1)):
            raise EditError(
                f"FillRegion: rectangle [{x0}, {y0}, {x1}, {y1}] is out of bounds "
                f"for grid {grid.w}x{grid.h}"
            )
        if value == 1:
            for obj in scene.objects:
                ox, oy = obj.pos
                if x0 <= ox <= x1 and y0 <= oy <= y1:
                    raise EditError(
                        f"FillRegion: cannot fill wall under object {obj.id!r} "
                        f"at [{ox}, {oy}]"
                    )
        return x0, y0, x1, y1, value

    def apply(self, scene: SceneGraph) -> SceneGraph:
        x0, y0, x1, y1, value = self._validate(scene)
        result = clone_scene(scene)
        for y in range(y0, y1 + 1):
            row = result.grid.tiles[y]
            for x in range(x0, x1 + 1):
                row[x] = value
        return result

    def inverse(self, scene: SceneGraph) -> "_RestoreRegion":
        x0, y0, x1, y1, _ = self._validate(scene)
        block = [
            [scene.grid.tiles[y][x] for x in range(x0, x1 + 1)]
            for y in range(y0, y1 + 1)
        ]
        return _RestoreRegion(x0=x0, y0=y0, block=block)

    def to_dict(self) -> dict[str, Any]:
        x0, y0, x1, y1 = self._rect()
        return {
            "op": self.op,
            "x0": x0,
            "y0": y0,
            "x1": x1,
            "y1": y1,
            "value": _as_int(self.value, "value"),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FillRegion":
        for key in ("x0", "y0", "x1", "y1", "value"):
            if key not in data:
                raise EditError(f"FillRegion: missing required field {key!r}: {data!r}")
        return cls(
            x0=_as_int(data["x0"], "x0"),
            y0=_as_int(data["y0"], "y0"),
            x1=_as_int(data["x1"], "x1"),
            y1=_as_int(data["y1"], "y1"),
            value=_as_int(data["value"], "value"),
        )


@register_op
@dataclass
class _RestoreRegion(EditOp):
    """Replay a captured rectangular block of prior tile values — inverse of a fill.

    Kept private to this module: a single-value fill cannot restore a block that
    mixed walls and floors, so the inverse needs an op that writes an arbitrary 2D
    block anchored at ``(x0, y0)``. It is serializable and self-inverting (re-capture)
    so the op-log stays JSON-clean.
    """

    op = "FillRegionRestore"

    x0: int
    y0: int
    block: list[list[int]]

    def _origin(self) -> tuple[int, int]:
        return _as_int(self.x0, "x0"), _as_int(self.y0, "y0")

    def _check_bounds(self, scene: SceneGraph) -> None:
        x0, y0 = self._origin()
        grid = scene.grid
        h = len(self.block)
        w = len(self.block[0]) if h else 0
        if h and not (grid.in_bounds(x0, y0) and grid.in_bounds(x0 + w - 1, y0 + h - 1)):
            raise EditError(
                f"FillRegionRestore: block at [{x0}, {y0}] ({w}x{h}) is out of bounds "
                f"for grid {grid.w}x{grid.h}"
            )

    def apply(self, scene: SceneGraph) -> SceneGraph:
        self._check_bounds(scene)
        x0, y0 = self._origin()
        result = clone_scene(scene)
        for dy, row in enumerate(self.block):
            tiles_row = result.grid.tiles[y0 + dy]
            for dx, value in enumerate(row):
                tiles_row[x0 + dx] = _as_int(value, "block value")
        return result

    def inverse(self, scene: SceneGraph) -> "_RestoreRegion":
        self._check_bounds(scene)
        x0, y0 = self._origin()
        prior = [
            [scene.grid.tiles[y0 + dy][x0 + dx] for dx in range(len(row))]
            for dy, row in enumerate(self.block)
        ]
        return _RestoreRegion(x0=x0, y0=y0, block=prior)

    def to_dict(self) -> dict[str, Any]:
        x0, y0 = self._origin()
        return {
            "op": self.op,
            "x0": x0,
            "y0": y0,
            "block": [[int(v) for v in row] for row in self.block],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_RestoreRegion":
        for key in ("x0", "y0", "block"):
            if key not in data:
                raise EditError(f"FillRegionRestore: missing required field {key!r}: {data!r}")
        block = [[int(v) for v in row] for row in data["block"]]
        return cls(x0=_as_int(data["x0"], "x0"), y0=_as_int(data["y0"], "y0"), block=block)
