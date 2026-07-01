"""Biome-dispatch chunk generator + world builder (Stage 4, ticket S4-T01).

The integration spine. :func:`build_world` wires a :class:`~envgen.infinite.MacroLayout`
into a runnable :class:`~envgen.infinite.InfiniteWorld` by composing a *dispatch*
:data:`~envgen.infinite.ChunkGen`: for each chunk it looks up the macro cell's biome,
fetches that biome's registered chunk generator, and delegates the tile fill to it —
falling back to the layout's ``fill_biome`` (then to ``flat``) for unauthored regions.

The macro layer owns *objects*, the micro layer owns *tiles* (the architecture's
coarse/fine split), so the dispatcher also attaches the macro cell's semantic objects
(those whose global position lands inside the chunk) onto the delegated chunk. This is
what makes ``InfiniteWorld.static_block_at`` / the window materializer see them.
"""
from __future__ import annotations

from typing import Optional

from envgen.infinite import (
    CHUNK,
    Chunk,
    ChunkCoord,
    ChunkGen,
    InfiniteWorld,
    MacroCell,
    MacroLayout,
)
from envgen.schema import SceneObject
from envgen.worldgen.base import get_biome, get_chunkgen

FALLBACK_CHUNKGEN = "flat"


def _resolve_chunkgen(biome_name: str) -> ChunkGen:
    """Chunk generator for ``biome_name``; ``flat`` if the biome/chunkgen is unknown.

    Unauthored space (``fill_biome`` defaults to ``"void"``, which registers no biome)
    resolves to the trivial all-floor fill, keeping the infinite plane traversable.
    """
    try:
        biome = get_biome(biome_name)
        return get_chunkgen(biome.chunkgen)
    except KeyError:
        return get_chunkgen(FALLBACK_CHUNKGEN)


def _objects_in_chunk(cell: Optional[MacroCell], cc: ChunkCoord) -> tuple[SceneObject, ...]:
    """Macro-cell objects whose *global* position falls inside chunk ``cc``."""
    if cell is None:
        return ()
    x0, y0 = cc[0] * CHUNK, cc[1] * CHUNK
    return tuple(
        o for o in cell.objects
        if x0 <= o.pos[0] < x0 + CHUNK and y0 <= o.pos[1] < y0 + CHUNK
    )


def biome_dispatch_gen(layout: MacroLayout) -> ChunkGen:
    """Build the dispatch :data:`~envgen.infinite.ChunkGen` closed over ``layout``.

    Pure per ``(chunk_seed, cc, cell)``: the closure only reads ``layout.fill_biome``
    (immutable for a given layout), so chunks stay seed-consistent and order-independent.
    """

    def dispatch(seed: int, cc: ChunkCoord, cell: Optional[MacroCell]) -> Chunk:
        biome_name = cell.biome if cell is not None else layout.fill_biome
        gen = _resolve_chunkgen(biome_name)
        base = gen(seed, cc, cell)
        objs = tuple(base.objects) + _objects_in_chunk(cell, cc)
        if objs == base.objects:
            return base
        return Chunk(cc=cc, grid=base.grid, objects=objs)

    return dispatch


def build_world(layout: MacroLayout, cache_size: int = 256) -> InfiniteWorld:
    """Materialize a runnable :class:`~envgen.infinite.InfiniteWorld` from ``layout``."""
    return InfiniteWorld(layout, biome_dispatch_gen(layout), cache_size=cache_size)
