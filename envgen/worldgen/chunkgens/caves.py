"""Caves chunk generator — cellular-automata caverns, edge-consistent (S4-T08).

Hash-noise seeded cellular automata carve organic caverns per chunk, a pure function
of ``(world_seed, cc)``. As with the maze generator, cross-chunk connectivity is
guaranteed by *coordinate-derived gates*: both neighbours carve a floor cell at the
same shared-border coordinate, and a carved skeleton wires every gate to the chunk
centre so caverns never seal a chunk off. The CA is decoration over that guaranteed
traversable spine. No global state.
"""
from __future__ import annotations

import hashlib
import random
from typing import Optional

from envgen.infinite import CHUNK, Chunk, ChunkCoord, MacroCell
from envgen.schema import Grid

_CENTER = CHUNK // 2 - 1
_INNER = CHUNK - 2
_FILL_PROB = 0.45
_CA_STEPS = 4


def _gate(tag: str, a: int, b: int) -> int:
    d = hashlib.blake2b(f"gate:{tag}:{a}:{b}".encode(), digest_size=4).digest()
    return 1 + int.from_bytes(d, "big") % _INNER


def gates(cc: ChunkCoord) -> dict[str, int]:
    cx, cy = cc
    return {
        "N": _gate("H", cx, cy),
        "S": _gate("H", cx, cy + 1),
        "W": _gate("V", cx, cy),
        "E": _gate("V", cx + 1, cy),
    }


def _wall_neighbors(tiles: list[list[int]], x: int, y: int) -> int:
    n = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if not (0 <= nx < CHUNK and 0 <= ny < CHUNK) or tiles[ny][nx] == 1:
                n += 1
    return n


def _cellular(tiles: list[list[int]], rng: random.Random) -> None:
    for y in range(1, CHUNK - 1):
        for x in range(1, CHUNK - 1):
            tiles[y][x] = 1 if rng.random() < _FILL_PROB else 0
    for _ in range(_CA_STEPS):
        snapshot = [row[:] for row in tiles]
        for y in range(1, CHUNK - 1):
            for x in range(1, CHUNK - 1):
                walls = sum(
                    snapshot[y + dy][x + dx] == 1
                    for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                    if not (dx == 0 and dy == 0)
                )
                tiles[y][x] = 1 if walls >= 5 else 0


def _carve_line(tiles: list[list[int]], x0: int, y0: int, x1: int, y1: int) -> None:
    if x0 == x1:
        for y in range(min(y0, y1), max(y0, y1) + 1):
            tiles[y][x0] = 0
    else:
        for x in range(min(x0, x1), max(x0, x1) + 1):
            tiles[y0][x] = 0


def _connect_gates(tiles: list[list[int]], g: dict[str, int]) -> None:
    c = _CENTER
    _carve_line(tiles, g["N"], 0, g["N"], c); _carve_line(tiles, g["N"], c, c, c)
    _carve_line(tiles, g["S"], CHUNK - 1, g["S"], c); _carve_line(tiles, g["S"], c, c, c)
    _carve_line(tiles, 0, g["W"], c, g["W"]); _carve_line(tiles, c, g["W"], c, c)
    _carve_line(tiles, CHUNK - 1, g["E"], c, g["E"]); _carve_line(tiles, c, g["E"], c, c)


def caves_chunk(seed: int, cc: ChunkCoord, cell: Optional[MacroCell] = None) -> Chunk:
    tiles = [[1] * CHUNK for _ in range(CHUNK)]
    _cellular(tiles, random.Random(seed))
    _connect_gates(tiles, gates(cc))
    return Chunk(cc=cc, grid=Grid(w=CHUNK, h=CHUNK, tiles=tiles), objects=())


from envgen.worldgen.base import register_chunkgen  # noqa: E402

register_chunkgen("caves", caves_chunk)
