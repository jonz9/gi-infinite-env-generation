"""Flat chunk generator — the trivial all-floor micro layer (Stage 4, ticket S4-T06).

The baseline the day-1 finite slice already implies: a ``CHUNK`` x ``CHUNK`` grid of
floor. Fully passable, trivially edge-consistent (every border tile is floor, so
neighbours always connect), and a pure function of nothing but its coords — the
control case for traversal / seed-consistency tests.

Semantic objects come from the *macro* layer (the dispatcher in
:mod:`envgen.worldgen.build` attaches ``macro_cell`` objects), so this micro
generator emits tiles only.
"""
from __future__ import annotations

from typing import Optional

from envgen.infinite import CHUNK, Chunk, ChunkCoord, MacroCell
from envgen.schema import Grid
from envgen.worldgen.base import register_chunkgen


def flat_grid() -> Grid:
    """A ``CHUNK`` x ``CHUNK`` all-floor grid."""
    return Grid(w=CHUNK, h=CHUNK, tiles=[[0] * CHUNK for _ in range(CHUNK)])


def flat_chunk(seed: int, cc: ChunkCoord, cell: Optional[MacroCell] = None) -> Chunk:
    """All-floor chunk. Ignores ``seed``/``cell`` — determinism is unconditional."""
    return Chunk(cc=cc, grid=flat_grid(), objects=())


register_chunkgen("flat", flat_chunk)
