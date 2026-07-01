"""Flooded-crypt biome — caverns seeded with Water hazards (Stage 4, ticket S4-T11).

A ``caves``-based region flooded with pools of Water (a hazard tile, kind ``Water``
from S4-T18). It registers its own ``flooded_caves`` chunk generator: it takes the
connected cavern from :func:`envgen.worldgen.chunkgens.caves.caves_chunk`, floods a
fraction of the cave floor with Water tiles, then **re-carves the gate corridors dry**
so a solvable spine always survives — routes must thread *around* the water, which the
lazy validator/solver enforce (Water is passable to the frozen finite nav but blocked
by the hazard-aware consumers). Pure per ``(world_seed, cc)``; no global state.
"""
from __future__ import annotations

import random
from typing import Optional

from envgen.infinite import CHUNK, Chunk, ChunkCoord, MacroCell
from envgen.schema import Grid
from envgen.worldgen.base import Biome, register_biome, register_chunkgen
from envgen.worldgen.chunkgens.caves import caves_chunk, gates
from envgen.worldgen.hazards import CODE_FOR_KIND

WATER = CODE_FOR_KIND["Water"]
_FLOOD_PROB = 0.30
_CENTER = CHUNK // 2 - 1


def _carve_line(tiles: list[list[int]], x0: int, y0: int, x1: int, y1: int) -> None:
    if x0 == x1:
        for y in range(min(y0, y1), max(y0, y1) + 1):
            tiles[y][x0] = 0
    else:
        for x in range(min(x0, x1), max(x0, x1) + 1):
            tiles[y0][x] = 0


def _recarve_gates(tiles: list[list[int]], g: dict[str, int]) -> None:
    """Re-open the four gate L-corridors to dry floor (a guaranteed solvable spine)."""
    c = _CENTER
    _carve_line(tiles, g["N"], 0, g["N"], c); _carve_line(tiles, g["N"], c, c, c)
    _carve_line(tiles, g["S"], CHUNK - 1, g["S"], c); _carve_line(tiles, g["S"], c, c, c)
    _carve_line(tiles, 0, g["W"], c, g["W"]); _carve_line(tiles, c, g["W"], c, c)
    _carve_line(tiles, CHUNK - 1, g["E"], c, g["E"]); _carve_line(tiles, c, g["E"], c, c)


def flooded_caves(seed: int, cc: ChunkCoord, cell: Optional[MacroCell] = None) -> Chunk:
    base = caves_chunk(seed, cc, cell)
    tiles = [row[:] for row in base.grid.tiles]
    rng = random.Random(seed ^ 0x5EA)   # distinct stream from the cave carve
    for y in range(1, CHUNK - 1):
        for x in range(1, CHUNK - 1):
            if tiles[y][x] == 0 and rng.random() < _FLOOD_PROB:
                tiles[y][x] = WATER
    _recarve_gates(tiles, gates(cc))
    return Chunk(cc=cc, grid=Grid(w=CHUNK, h=CHUNK, tiles=tiles), objects=())


register_chunkgen("flooded_caves", flooded_caves)
register_biome(Biome(
    name="flooded_crypt",
    chunkgen="flooded_caves",
    description="water-flooded caverns; routes must skirt the hazard pools",
))
