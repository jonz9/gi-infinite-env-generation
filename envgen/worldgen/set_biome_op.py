"""``SetBiome`` macro-op — repaint a region's biome (Stage 4, ticket S4-T05).

Sets/replaces the biome of one or more :class:`~envgen.infinite.MacroCell`s. Like
``Extend`` it is a *pure transform* (clone → modify, input untouched) with plain-JSON
``to_dict``/``from_dict``, so it slots into the same deterministic macro op-log. It
reports :meth:`affected_chunks` so a session can invalidate *only* those chunks in the
world cache rather than rebuilding everything. Existing semantic objects on a repainted
cell are preserved — only the terrain style changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from envgen.infinite import ChunkCoord, MacroCell, MacroLayout


@dataclass(frozen=True)
class SetBiome:
    """Set ``biome`` on every chunk coord in ``cells``."""

    biome: str
    cells: tuple[ChunkCoord, ...]

    def __post_init__(self) -> None:
        if not self.cells:
            raise ValueError("SetBiome needs at least one target cell")

    @classmethod
    def cell(cls, biome: str, cc: ChunkCoord) -> "SetBiome":
        """Convenience: repaint a single chunk."""
        return cls(biome=biome, cells=(cc,))

    @classmethod
    def region(cls, biome: str, x0: int, y0: int, x1: int, y1: int) -> "SetBiome":
        """Repaint the inclusive rectangle of chunk coords ``[x0..x1] x [y0..y1]``."""
        cells = tuple(
            (cx, cy)
            for cy in range(min(y0, y1), max(y0, y1) + 1)
            for cx in range(min(x0, x1), max(x0, x1) + 1)
        )
        return cls(biome=biome, cells=cells)

    def affected_chunks(self, layout: MacroLayout | None = None) -> set[ChunkCoord]:
        """Chunks whose biome (and thus terrain) this op changes."""
        return set(self.cells)

    def apply(self, layout: MacroLayout) -> MacroLayout:
        """Return a clone of ``layout`` with the target cells repainted (objects kept)."""
        cells = dict(layout.cells)
        for cc in self.cells:
            existing = layout.cells.get(cc)
            objects = existing.objects if existing is not None else ()
            cells[cc] = MacroCell(biome=self.biome, objects=objects)
        return MacroLayout(
            seed=layout.seed, cells=cells, goal=layout.goal, fill_biome=layout.fill_biome
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": "SetBiome",
            "biome": self.biome,
            "cells": [[cx, cy] for cx, cy in self.cells],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SetBiome":
        if data.get("op") != "SetBiome":
            raise ValueError(f"not a SetBiome op: {data.get('op')!r}")
        cells = tuple((int(x), int(y)) for x, y in data["cells"])
        return cls(biome=data["biome"], cells=cells)
