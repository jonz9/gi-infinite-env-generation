"""Maze chunk generator — per-chunk maze with edge-consistent exits (S4-T07).

A randomized-DFS (recursive backtracker) maze carved from the per-chunk seed, so each
chunk's interior varies by ``(world_seed, cc)`` yet is a pure function of it. The hard
part is **cross-chunk connectivity**: two neighbouring chunks must agree on where their
shared border is passable. We solve it with *coordinate-derived gates* — the passable
column/row on each border is a hash of the border's canonical identity (independent of
which chunk computes it), so both neighbours carve a floor cell at the same global
coordinate and the mazes connect. Each gate is then wired to the chunk centre, so every
gate (and thus the whole maze) is mutually reachable. No global state.
"""
from __future__ import annotations

import hashlib
import random
from typing import Optional

from envgen.infinite import CHUNK, Chunk, ChunkCoord, MacroCell
from envgen.schema import Grid

_CENTER = CHUNK // 2 - 1          # 7 for CHUNK=16 — an odd interior maze cell
_INNER = CHUNK - 2               # gates live in [1, CHUNK-2]


def _gate(tag: str, a: int, b: int) -> int:
    """Deterministic passable index on a shared border, from its canonical key."""
    d = hashlib.blake2b(f"gate:{tag}:{a}:{b}".encode(), digest_size=4).digest()
    return 1 + int.from_bytes(d, "big") % _INNER


def gates(cc: ChunkCoord) -> dict[str, int]:
    """The four border gate offsets for chunk ``cc`` (shared with each neighbour)."""
    cx, cy = cc
    return {
        "N": _gate("H", cx, cy),        # top row: line shared with (cx, cy-1)'s south
        "S": _gate("H", cx, cy + 1),    # bottom row: shared with (cx, cy+1)'s north
        "W": _gate("V", cx, cy),        # left col: shared with (cx-1, cy)'s east
        "E": _gate("V", cx + 1, cy),    # right col: shared with (cx+1, cy)'s west
    }


def _carve_maze(tiles: list[list[int]], rng: random.Random) -> None:
    """Recursive-backtracker maze over odd interior cells (fully connected)."""
    start = (1, 1)
    tiles[1][1] = 0
    stack = [start]
    while stack:
        x, y = stack[-1]
        steps = [(2, 0), (-2, 0), (0, 2), (0, -2)]
        rng.shuffle(steps)
        for dx, dy in steps:
            nx, ny = x + dx, y + dy
            if 1 <= nx <= CHUNK - 2 and 1 <= ny <= CHUNK - 2 and tiles[ny][nx] == 1:
                tiles[y + dy // 2][x + dx // 2] = 0   # knock out the wall between
                tiles[ny][nx] = 0
                stack.append((nx, ny))
                break
        else:
            stack.pop()


def _carve_line(tiles: list[list[int]], x0: int, y0: int, x1: int, y1: int) -> None:
    """Carve a straight horizontal or vertical floor segment (inclusive)."""
    if x0 == x1:
        for y in range(min(y0, y1), max(y0, y1) + 1):
            tiles[y][x0] = 0
    else:
        for x in range(min(x0, x1), max(x0, x1) + 1):
            tiles[y0][x] = 0


def _connect_gates(tiles: list[list[int]], g: dict[str, int]) -> None:
    """Wire each border gate to the chunk centre via an L-corridor."""
    c = _CENTER
    # North gate down to centre row, then across to centre.
    _carve_line(tiles, g["N"], 0, g["N"], c); _carve_line(tiles, g["N"], c, c, c)
    _carve_line(tiles, g["S"], CHUNK - 1, g["S"], c); _carve_line(tiles, g["S"], c, c, c)
    _carve_line(tiles, 0, g["W"], c, g["W"]); _carve_line(tiles, c, g["W"], c, c)
    _carve_line(tiles, CHUNK - 1, g["E"], c, g["E"]); _carve_line(tiles, c, g["E"], c, c)


def maze_chunk(seed: int, cc: ChunkCoord, cell: Optional[MacroCell] = None) -> Chunk:
    tiles = [[1] * CHUNK for _ in range(CHUNK)]
    _carve_maze(tiles, random.Random(seed))
    _connect_gates(tiles, gates(cc))
    return Chunk(cc=cc, grid=Grid(w=CHUNK, h=CHUNK, tiles=tiles), objects=())


from envgen.worldgen.base import register_chunkgen  # noqa: E402

register_chunkgen("maze", maze_chunk)
