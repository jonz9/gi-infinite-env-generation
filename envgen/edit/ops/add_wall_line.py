"""AddWallLine — draw a straight wall segment between two collinear cells (S1-T13).

Self-registering :class:`~envgen.edit.base.EditOp` under the ``"AddWallLine"`` key.
Given two grid cells ``a=[x, y]`` and ``b=[x, y]`` that share a row (horizontal) or
a column (vertical), it sets every cell on the inclusive segment to wall (``1``).

Rejected with a specific :class:`~envgen.edit.base.EditError`:

* **non-collinear** endpoints (neither ``x`` nor ``y`` equal) — only axis-aligned
  segments are wall lines;
* **out-of-bounds** endpoints;
* walling a cell currently **occupied by an object** (the object layer would be
  buried inside a wall).

Application is pure — the result is built from ``clone_scene(scene)`` (which
deep-copies the tile rows) so the input scene is never mutated.

``inverse`` restores the exact prior tile values along the line; because writing a
wall is lossy, the inverse is a companion :class:`_RestoreTiles` op that replays the
captured ``(x, y, value)`` writes, keeping the op-log JSON-clean.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from envgen.edit.base import EditError, EditOp, clone_scene, register_op
from envgen.schema import SceneGraph

_WALL = 1


def _as_cell(value: Any, name: str) -> tuple[int, int]:
    """Coerce ``value`` into an ``(x, y)`` int tuple or raise EditError."""
    if not (isinstance(value, (list, tuple)) and len(value) == 2):
        raise EditError(f"AddWallLine: {name} must be [x, y], got {value!r}")
    try:
        return (int(value[0]), int(value[1]))
    except (TypeError, ValueError):
        raise EditError(f"AddWallLine: {name} must be integer [x, y], got {value!r}")


def _line_cells(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """Inclusive cells of the axis-aligned segment from ``a`` to ``b``.

    Caller guarantees collinearity (shared row or column).
    """
    ax, ay = a
    bx, by = b
    if ay == by:  # horizontal
        step = 1 if bx >= ax else -1
        return [(x, ay) for x in range(ax, bx + step, step)]
    step = 1 if by >= ay else -1  # vertical (ax == bx)
    return [(ax, y) for y in range(ay, by + step, step)]


@register_op
@dataclass
class AddWallLine(EditOp):
    """Set every cell on the collinear segment ``a``..``b`` to wall (``1``)."""

    op = "AddWallLine"

    a: tuple[int, int]
    b: tuple[int, int]

    def _endpoints(self) -> tuple[tuple[int, int], tuple[int, int]]:
        return _as_cell(self.a, "a"), _as_cell(self.b, "b")

    def _validated_cells(self, scene: SceneGraph) -> list[tuple[int, int]]:
        a, b = self._endpoints()
        grid = scene.grid
        for cell, name in ((a, "a"), (b, "b")):
            if not grid.in_bounds(*cell):
                raise EditError(
                    f"AddWallLine: endpoint {name}={list(cell)} is out of bounds "
                    f"for grid {grid.w}x{grid.h}"
                )
        if a[0] != b[0] and a[1] != b[1]:
            raise EditError(
                f"AddWallLine: endpoints {list(a)} and {list(b)} are not collinear; "
                "a wall line must share a row (horizontal) or column (vertical)"
            )
        cells = _line_cells(a, b)
        occupied = {obj.pos: obj.id for obj in scene.objects}
        for cell in cells:
            if cell in occupied:
                raise EditError(
                    f"AddWallLine: cell {list(cell)} is occupied by object "
                    f"{occupied[cell]!r}; cannot wall over an object"
                )
        return cells

    def apply(self, scene: SceneGraph) -> SceneGraph:
        cells = self._validated_cells(scene)
        result = clone_scene(scene)
        for x, y in cells:
            result.grid.tiles[y][x] = _WALL
        return result

    def inverse(self, scene: SceneGraph) -> "_RestoreTiles":
        cells = self._validated_cells(scene)
        grid = scene.grid
        writes = [(x, y, grid.tiles[y][x]) for x, y in cells]
        return _RestoreTiles(writes=writes)

    def to_dict(self) -> dict[str, Any]:
        a, b = self._endpoints()
        return {"op": self.op, "a": [a[0], a[1]], "b": [b[0], b[1]]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AddWallLine":
        for key in ("a", "b"):
            if key not in data:
                raise EditError(f"AddWallLine: missing required field {key!r}: {data!r}")
        return cls(a=_as_cell(data["a"], "a"), b=_as_cell(data["b"], "b"))


@register_op
@dataclass
class _RestoreTiles(EditOp):
    """Replay captured ``(x, y, value)`` tile writes — inverse of an AddWallLine.

    Kept private to this module: AddWallLine's structural inverse needs an op that
    can set tiles to *arbitrary* prior values, which a wall-only write cannot. It is
    serializable and self-inverting via re-capture so the op-log stays JSON-clean.
    """

    op = "AddWallLineRestore"

    writes: list[tuple[int, int, int]]

    def apply(self, scene: SceneGraph) -> SceneGraph:
        result = clone_scene(scene)
        grid = result.grid
        for x, y, value in self.writes:
            if not grid.in_bounds(x, y):
                raise EditError(
                    f"AddWallLineRestore: cell [{x}, {y}] out of bounds "
                    f"for grid {grid.w}x{grid.h}"
                )
            grid.tiles[y][x] = value
        return result

    def inverse(self, scene: SceneGraph) -> "_RestoreTiles":
        grid = scene.grid
        prior = [
            (x, y, grid.tiles[y][x])
            for x, y, _ in self.writes
            if grid.in_bounds(x, y)
        ]
        return _RestoreTiles(writes=prior)

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, "writes": [[x, y, v] for x, y, v in self.writes]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_RestoreTiles":
        if "writes" not in data:
            raise EditError(f"AddWallLineRestore: missing 'writes': {data!r}")
        writes: list[tuple[int, int, int]] = []
        for item in data["writes"]:
            if not (isinstance(item, (list, tuple)) and len(item) == 3):
                raise EditError(
                    f"AddWallLineRestore: each write must be [x, y, value], got {item!r}"
                )
            writes.append((int(item[0]), int(item[1]), int(item[2])))
        return cls(writes=writes)
