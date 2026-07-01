"""Rooms chunk generator — dungeon rooms + corridors, edge-consistent (S4-T09).

Dungeon-style rectangular rooms joined by corridors, carved per chunk from its seed.
Border doorways align across chunks via the same *coordinate-derived gates* the maze /
caves generators use, so rooms connect chunk-to-chunk. A central room anchors the four
gate corridors (guaranteeing every gate is mutually reachable); extra rooms are wired
back to that spine. Pure per ``(world_seed, cc)``; no global state.
"""
from __future__ import annotations

import hashlib
import random
from typing import Optional

from envgen.infinite import CHUNK, Chunk, ChunkCoord, MacroCell
from envgen.schema import Grid

_CENTER = CHUNK // 2 - 1
_INNER = CHUNK - 2


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


def _carve_room(tiles: list[list[int]], cx: int, cy: int, rw: int, rh: int) -> None:
    """Carve a floor rectangle centred on ``(cx, cy)``, clipped to the interior."""
    for y in range(max(1, cy - rh // 2), min(CHUNK - 1, cy + rh // 2 + 1)):
        for x in range(max(1, cx - rw // 2), min(CHUNK - 1, cx + rw // 2 + 1)):
            tiles[y][x] = 0


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


def rooms_chunk(seed: int, cc: ChunkCoord, cell: Optional[MacroCell] = None) -> Chunk:
    tiles = [[1] * CHUNK for _ in range(CHUNK)]
    rng = random.Random(seed)
    _carve_room(tiles, _CENTER, _CENTER, 4, 4)          # central anchor room
    for _ in range(rng.randint(2, 4)):
        rx, ry = rng.randint(3, CHUNK - 4), rng.randint(3, CHUNK - 4)
        _carve_room(tiles, rx, ry, rng.randint(3, 5), rng.randint(3, 5))
        _carve_line(tiles, rx, ry, _CENTER, ry)          # corridor back to the spine
        _carve_line(tiles, _CENTER, ry, _CENTER, _CENTER)
    _connect_gates(tiles, gates(cc))
    return Chunk(cc=cc, grid=Grid(w=CHUNK, h=CHUNK, tiles=tiles), objects=())


from envgen.worldgen.base import register_chunkgen  # noqa: E402

register_chunkgen("rooms", rooms_chunk)
