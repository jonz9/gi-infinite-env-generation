"""Swamp biome — open low-density traversal region (Stage 4, ticket S4-T12).

An open, all-floor expanse scattered with Table obstacles — the easy traversal biome
between the puzzle (armory) and hazard (flooded_crypt) regions. It registers a
``swampland`` chunk generator: an open flat chunk with a handful of seeded Tables
(blocking :class:`~envgen.schema.SceneObject`s at global coords, so the agent detours
around them on open ground). Fully passable floor makes every border trivially
edge-consistent. Pure per ``(world_seed, cc)``; no global state.
"""
from __future__ import annotations

import random
from typing import Optional

from envgen.infinite import CHUNK, Chunk, ChunkCoord, MacroCell
from envgen.schema import EntityType, Grid, SceneObject
from envgen.worldgen.base import Biome, register_biome, register_chunkgen


def swampland(seed: int, cc: ChunkCoord, cell: Optional[MacroCell] = None) -> Chunk:
    tiles = [[0] * CHUNK for _ in range(CHUNK)]   # open floor, no walls
    rng = random.Random(seed ^ 0x5A3)
    ox, oy = cc[0] * CHUNK, cc[1] * CHUNK
    seen: set[tuple[int, int]] = set()
    objects: list[SceneObject] = []
    for i in range(rng.randint(2, 5)):
        lx, ly = rng.randint(1, CHUNK - 2), rng.randint(1, CHUNK - 2)
        if (lx, ly) in seen:
            continue
        seen.add((lx, ly))
        objects.append(SceneObject(
            id=f"swamp_t_{cc[0]}_{cc[1]}_{i}",
            type=EntityType.TABLE,
            pos=(ox + lx, oy + ly),
        ))
    return Chunk(cc=cc, grid=Grid(w=CHUNK, h=CHUNK, tiles=tiles), objects=tuple(objects))


register_chunkgen("swampland", swampland)
register_biome(Biome(
    name="swamp",
    chunkgen="swampland",
    description="open floor scattered with Table obstacles; the low-density traversal biome",
))
