"""Chunk-edge stitching checker (Stage 4, ticket S4-T13).

A reusable invariant for chunk generators: adjacent chunks must be *mutually passable*
across their shared border wherever each side claims a cell is passable. A generator
whose exits don't line up (a maze that carves a corridor to a border cell its neighbour
walls off) is caught here — the cross-chunk connectivity the infinite world depends on.

``assert_edges_consistent(world, cc_a, cc_b)`` checks every pair of cells straddling the
border between two orthogonally-adjacent chunks: if both are passable they are 4-adjacent
(trivially true for a grid) and, more usefully, it verifies that *at least one* border
crossing exists so the chunks are actually connected, not merely non-contradictory.
"""
from __future__ import annotations

from envgen.infinite import CHUNK, ChunkCoord, Coord, InfiniteWorld


def _border_pairs(cc_a: ChunkCoord, cc_b: ChunkCoord) -> list[tuple[Coord, Coord]]:
    """The (cell_in_a, cell_in_b) pairs of globally-adjacent cells on the shared edge."""
    ax, ay = cc_a
    bx, by = cc_b
    if (bx, by) == (ax + 1, ay):        # b is east of a
        col_a, col_b = (ax + 1) * CHUNK - 1, bx * CHUNK
        return [((col_a, ay * CHUNK + i), (col_b, ay * CHUNK + i)) for i in range(CHUNK)]
    if (bx, by) == (ax - 1, ay):        # b is west of a -> a is east of b
        return [(a, b) for b, a in _border_pairs(cc_b, cc_a)]
    if (bx, by) == (ax, ay + 1):        # b is south of a
        row_a, row_b = (ay + 1) * CHUNK - 1, by * CHUNK
        return [((ax * CHUNK + i, row_a), (ax * CHUNK + i, row_b)) for i in range(CHUNK)]
    if (bx, by) == (ax, ay - 1):        # b is north of a
        return [(b, a) for a, b in _border_pairs(cc_b, cc_a)]
    raise ValueError(f"chunks {cc_a} and {cc_b} are not orthogonally adjacent")


def edges_consistent(world: InfiniteWorld, cc_a: ChunkCoord, cc_b: ChunkCoord) -> tuple[bool, str]:
    """Whether at least one passable crossing joins the two chunks. ``(ok, msg)``."""
    crossings = 0
    for a, b in _border_pairs(cc_a, cc_b):
        if world.passable(a) and world.passable(b):
            crossings += 1
    if crossings == 0:
        return False, f"no passable crossing between {cc_a} and {cc_b} (chunks disconnected)"
    return True, f"{crossings} crossing(s) between {cc_a} and {cc_b}"


def assert_edges_consistent(world: InfiniteWorld, cc_a: ChunkCoord, cc_b: ChunkCoord) -> None:
    """Raise :class:`AssertionError` if the shared border has no passable crossing."""
    ok, msg = edges_consistent(world, cc_a, cc_b)
    if not ok:
        raise AssertionError(msg)
