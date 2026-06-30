"""ConnectCorridor — carve a width-1 floor corridor between two cells (S1-T11).

Self-registering :class:`~envgen.edit.base.EditOp` under the ``"ConnectCorridor"``
key. Given two grid cells ``a=[x, y]`` and ``b=[x, y]`` it carves a deterministic
L-shaped (horizontal-then-vertical) width-1 path, setting every intervening tile to
floor (``0``). A straight run (shared row or column) is the degenerate L. Endpoints
out of bounds are rejected with a specific :class:`~envgen.edit.base.EditError`.

Application is pure — the result is built from ``clone_scene(scene)`` (which
deep-copies the tile rows) so the input scene is never mutated.

``inverse`` restores the exact prior tile values along the carved path; because a
floor carve is lossy (it forgets whatever was there), the inverse is a companion
:class:`_RestoreTiles` op that replays the captured ``(x, y, value)`` writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from envgen.edit.base import EditError, EditOp, clone_scene, register_op
from envgen.schema import SceneGraph

_FLOOR = 0


def _as_cell(value: Any, name: str) -> tuple[int, int]:
    """Coerce ``value`` into an ``(x, y)`` int tuple or raise EditError."""
    if not (isinstance(value, (list, tuple)) and len(value) == 2):
        raise EditError(f"ConnectCorridor: {name} must be [x, y], got {value!r}")
    try:
        return (int(value[0]), int(value[1]))
    except (TypeError, ValueError):
        raise EditError(f"ConnectCorridor: {name} must be integer [x, y], got {value!r}")


def _corridor_cells(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """Deterministic L-shaped path cells: horizontal along ``a``'s row, then vertical.

    Cells are returned in walk order with no duplicates (the corner is shared).
    """
    ax, ay = a
    bx, by = b
    cells: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    def add(x: int, y: int) -> None:
        if (x, y) not in seen:
            seen.add((x, y))
            cells.append((x, y))

    step_x = 1 if bx >= ax else -1
    for x in range(ax, bx + step_x, step_x):
        add(x, ay)
    step_y = 1 if by >= ay else -1
    for y in range(ay, by + step_y, step_y):
        add(bx, y)
    return cells


@register_op
@dataclass
class ConnectCorridor(EditOp):
    """Carve a width-1 floor corridor from cell ``a`` to cell ``b`` (L-shaped)."""

    op = "ConnectCorridor"

    a: tuple[int, int]
    b: tuple[int, int]

    def _endpoints(self) -> tuple[tuple[int, int], tuple[int, int]]:
        return _as_cell(self.a, "a"), _as_cell(self.b, "b")

    def apply(self, scene: SceneGraph) -> SceneGraph:
        a, b = self._endpoints()
        grid = scene.grid
        for cell, name in ((a, "a"), (b, "b")):
            if not grid.in_bounds(*cell):
                raise EditError(
                    f"ConnectCorridor: endpoint {name}={list(cell)} is out of bounds "
                    f"for grid {grid.w}x{grid.h}"
                )
        result = clone_scene(scene)
        for x, y in _corridor_cells(a, b):
            result.grid.tiles[y][x] = _FLOOR
        return result

    def inverse(self, scene: SceneGraph) -> "_RestoreTiles":
        a, b = self._endpoints()
        grid = scene.grid
        writes: list[tuple[int, int, int]] = []
        for x, y in _corridor_cells(a, b):
            if grid.in_bounds(x, y):
                writes.append((x, y, grid.tiles[y][x]))
        return _RestoreTiles(writes=writes)

    def to_dict(self) -> dict[str, Any]:
        a, b = self._endpoints()
        return {"op": self.op, "a": [a[0], a[1]], "b": [b[0], b[1]]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConnectCorridor":
        for key in ("a", "b"):
            if key not in data:
                raise EditError(f"ConnectCorridor: missing required field {key!r}: {data!r}")
        return cls(a=_as_cell(data["a"], "a"), b=_as_cell(data["b"], "b"))


@register_op
@dataclass
class _RestoreTiles(EditOp):
    """Replay captured ``(x, y, value)`` tile writes — inverse of a corridor carve.

    Kept private to this module (the corridor's structural inverse needs an op that
    can set tiles to *arbitrary* prior values, which a floor-only carve cannot). It
    is serializable and self-inverting via re-capture so the op-log stays JSON-clean.
    """

    op = "ConnectCorridorRestore"

    writes: list[tuple[int, int, int]]

    def apply(self, scene: SceneGraph) -> SceneGraph:
        result = clone_scene(scene)
        grid = result.grid
        for x, y, value in self.writes:
            if not grid.in_bounds(x, y):
                raise EditError(
                    f"ConnectCorridorRestore: cell [{x}, {y}] out of bounds "
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
            raise EditError(f"ConnectCorridorRestore: missing 'writes': {data!r}")
        writes: list[tuple[int, int, int]] = []
        for item in data["writes"]:
            if not (isinstance(item, (list, tuple)) and len(item) == 3):
                raise EditError(
                    f"ConnectCorridorRestore: each write must be [x, y, value], got {item!r}"
                )
            writes.append((int(item[0]), int(item[1]), int(item[2])))
        return cls(writes=writes)
