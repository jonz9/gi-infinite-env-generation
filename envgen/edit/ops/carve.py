"""Carve — set individual grid cells to floor(0) or wall(1) (S1-T05).

Self-registering :class:`~envgen.edit.base.EditOp` under the ``"Carve"`` key. Given
a list of cells ``[[x, y], ...]`` and a target tile value (``0`` = floor, ``1`` =
wall) it writes that value into every named cell of ``grid.tiles``. Out-of-bounds
cells are rejected, as is carving a wall (``1``) under a cell occupied by an
existing object — that would trap/erase the object's footprint. Both raise a
specific :class:`~envgen.edit.base.EditError` that feeds the repair loop.

Application is pure — the result is built from ``clone_scene(scene)`` (which
deep-copies the tile rows) so the input scene is never mutated.

``inverse`` restores the exact prior tile values at the carved cells (read from the
pre-state); since a carve is lossy it is undone by a companion :class:`_CarveRestore`
op that replays the captured ``(x, y, value)`` writes, keeping the op-log JSON-clean.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from envgen.edit.base import EditError, EditOp, clone_scene, register_op
from envgen.schema import SceneGraph

_FLOOR = 0
_WALL = 1


def _as_cell(value: Any, name: str) -> tuple[int, int]:
    """Coerce ``value`` into an ``(x, y)`` int tuple or raise EditError."""
    if not (isinstance(value, (list, tuple)) and len(value) == 2):
        raise EditError(f"Carve: {name} must be [x, y], got {value!r}")
    try:
        return (int(value[0]), int(value[1]))
    except (TypeError, ValueError):
        raise EditError(f"Carve: {name} must be integer [x, y], got {value!r}")


def _as_cells(value: Any) -> list[tuple[int, int]]:
    """Coerce ``value`` into a list of ``(x, y)`` cells or raise EditError."""
    if not isinstance(value, (list, tuple)):
        raise EditError(f"Carve: cells must be a list of [x, y], got {value!r}")
    return [_as_cell(c, "cell") for c in value]


def _as_tile(value: Any) -> int:
    """Coerce ``value`` into a tile value (0 or 1) or raise EditError."""
    try:
        tile = int(value)
    except (TypeError, ValueError):
        raise EditError(f"Carve: tile must be 0 (floor) or 1 (wall), got {value!r}")
    if tile not in (_FLOOR, _WALL):
        raise EditError(f"Carve: tile must be 0 (floor) or 1 (wall), got {tile!r}")
    return tile


@register_op
@dataclass
class Carve(EditOp):
    """Set each cell in ``cells`` of ``grid.tiles`` to ``tile`` (0=floor, 1=wall)."""

    op = "Carve"

    cells: list[tuple[int, int]]
    tile: int

    def _parsed(self) -> tuple[list[tuple[int, int]], int]:
        return _as_cells(self.cells), _as_tile(self.tile)

    def apply(self, scene: SceneGraph) -> SceneGraph:
        cells, tile = self._parsed()
        grid = scene.grid
        occupied = {(o.pos[0], o.pos[1]) for o in scene.objects}
        for x, y in cells:
            if not grid.in_bounds(x, y):
                raise EditError(
                    f"Carve: cell [{x}, {y}] is out of bounds for grid "
                    f"{grid.w}x{grid.h}"
                )
            if tile == _WALL and (x, y) in occupied:
                raise EditError(
                    f"Carve: cannot carve a wall at [{x}, {y}] — an object occupies "
                    f"that cell"
                )
        result = clone_scene(scene)
        for x, y in cells:
            result.grid.tiles[y][x] = tile
        return result

    def inverse(self, scene: SceneGraph) -> "_CarveRestore":
        cells, _ = self._parsed()
        grid = scene.grid
        writes = [
            (x, y, grid.tiles[y][x]) for x, y in cells if grid.in_bounds(x, y)
        ]
        return _CarveRestore(writes=writes)

    def to_dict(self) -> dict[str, Any]:
        cells, tile = self._parsed()
        return {"op": self.op, "cells": [[x, y] for x, y in cells], "tile": tile}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Carve":
        for key in ("cells", "tile"):
            if key not in data:
                raise EditError(f"Carve: missing required field {key!r}: {data!r}")
        return cls(cells=_as_cells(data["cells"]), tile=_as_tile(data["tile"]))


@register_op
@dataclass
class _CarveRestore(EditOp):
    """Replay captured ``(x, y, value)`` tile writes — inverse of a carve.

    Kept private to this module: a carve forgets the prior tile values, so undoing
    it needs an op that can set tiles to *arbitrary* prior values rather than a
    single target. It is serializable and self-inverting via re-capture so the
    op-log stays JSON-clean.
    """

    op = "CarveRestore"

    writes: list[tuple[int, int, int]]

    def apply(self, scene: SceneGraph) -> SceneGraph:
        result = clone_scene(scene)
        grid = result.grid
        for x, y, value in self.writes:
            if not grid.in_bounds(x, y):
                raise EditError(
                    f"CarveRestore: cell [{x}, {y}] out of bounds for grid "
                    f"{grid.w}x{grid.h}"
                )
            grid.tiles[y][x] = value
        return result

    def inverse(self, scene: SceneGraph) -> "_CarveRestore":
        grid = scene.grid
        prior = [
            (x, y, grid.tiles[y][x])
            for x, y, _ in self.writes
            if grid.in_bounds(x, y)
        ]
        return _CarveRestore(writes=prior)

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, "writes": [[x, y, v] for x, y, v in self.writes]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_CarveRestore":
        if "writes" not in data:
            raise EditError(f"CarveRestore: missing 'writes': {data!r}")
        writes: list[tuple[int, int, int]] = []
        for item in data["writes"]:
            if not (isinstance(item, (list, tuple)) and len(item) == 3):
                raise EditError(
                    f"CarveRestore: each write must be [x, y, value], got {item!r}"
                )
            writes.append((int(item[0]), int(item[1]), int(item[2])))
        return cls(writes=writes)
