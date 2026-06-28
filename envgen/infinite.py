"""Infinite-world extension — a world as a pure function of (seed, coords).

FORWARD-LOOKING SKETCH (not on the day-1 path). The canonical finite pipeline is
``schema.SceneGraph`` -> ``world.World``. This module is the *infinite* generalization
the brief literally asks for ("infinite procedural environment generation"), borrowed
from InfiniteDiffusion (SIGGRAPH '26, arXiv 2512.08309): a world is a pure function
``world(seed, x, y) -> tile`` — seed-consistent, O(1) random access, lazily evaluated
with bounded memory. We keep its *interface*, not its diffusion model.

It deliberately reuses the canonical IR types (``EntityType``, ``SceneObject``,
``Grid``) rather than forking them — there is exactly one scene-object vocabulary.

Two layers, mirroring InfiniteDiffusion's coarse-to-fine Laplacian cascade:
  - Macro (LLM, low-freq): a small finite ``MacroLayout`` — a biome per chunk plus the
    semantic ``SceneObject``s it carries. The LLM authors this; it never draws tiles.
  - Micro (deterministic, high-freq): a pure ``ChunkGen`` fills the actual tiles per
    chunk. Order-independent, so chunks are seed-consistent and randomly accessible.

A finite ``SceneGraph`` is just the special case of a one-chunk layout — so the day-1
ASCII slice and this share the same object vocabulary and navigation code.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

from envgen.schema import BLOCKING_TYPES, EntityType, Grid, SceneObject

Coord = tuple[int, int]        # global tile coordinate (x, y)
ChunkCoord = tuple[int, int]   # chunk index (cx, cy)

CHUNK = 16                     # tiles per chunk edge


# --- Macro layer (LLM-authored, finite, small) --------------------------------
@dataclass(frozen=True)
class MacroCell:
    """One coarse region: a biome plus the canonical objects it carries."""

    biome: str                                # "armory" | "flooded_crypt" | "swamp"
    objects: tuple[SceneObject, ...] = ()


@dataclass
class MacroLayout:
    """Low-res semantic map: the coarse model / low-frequency component.

    Sparse — only authored chunks appear in ``cells``; the rest is ``fill_biome``.
    """

    seed: int
    cells: dict[ChunkCoord, MacroCell] = field(default_factory=dict)
    goal: str = "reach exit"
    fill_biome: str = "void"

    def cell(self, cc: ChunkCoord) -> Optional[MacroCell]:
        return self.cells.get(cc)

    def objects(self) -> list[SceneObject]:
        """Every semantic object across authored cells."""
        return [o for cell in self.cells.values() for o in cell.objects]


# --- Micro layer (deterministic chunk function) -------------------------------
@dataclass(frozen=True)
class Chunk:
    """A CHUNK x CHUNK tile grid plus the objects landing in it (high-freq residual)."""

    cc: ChunkCoord
    grid: Grid                                  # always CHUNK x CHUNK
    objects: tuple[SceneObject, ...] = ()


# A ChunkGen is a PURE function: (per-chunk seed, chunk coord, macro cell|None) -> Chunk.
# Concrete generators (hash-noise, per-chunk WFC, maze carver) implement this.
ChunkGen = Callable[[int, ChunkCoord, Optional[MacroCell]], Chunk]


def chunk_seed(seed: int, cc: ChunkCoord) -> int:
    """Per-chunk seed from world seed + coords.

    Content depends only on ``(seed, cc)``, never on visit order — this is what gives
    seed-consistency and order-independent random access.
    """
    digest = hashlib.blake2b(f"{seed}:{cc[0]}:{cc[1]}".encode(), digest_size=8)
    return int.from_bytes(digest.digest(), "big")


# --- InfiniteWorld: world(seed, coords) -> tile, lazy & unbounded -------------
class InfiniteWorld:
    """Infinite, seed-consistent, O(1)-random-access world.

    Chunks are materialized on demand and evicted under a bounded LRU cache
    (InfiniteDiffusion's "visible region + bounded transient cache"): memory stays
    O(cache_size) no matter how far the agent or validator roams.

    Exposes the same ``passable`` / ``neighbors`` surface the finite ``World`` does, so
    the navigator in :mod:`envgen.navigate` runs unchanged on either.
    """

    def __init__(self, layout: MacroLayout, gen: ChunkGen, cache_size: int = 256) -> None:
        self._layout = layout
        self._gen = gen
        self._cache: "OrderedDict[ChunkCoord, Chunk]" = OrderedDict()
        self._cache_size = cache_size

    @property
    def layout(self) -> MacroLayout:
        return self._layout

    def chunk(self, cc: ChunkCoord) -> Chunk:
        """Fetch (or lazily materialize) a chunk. O(1) amortized, order-independent."""
        hit = self._cache.get(cc)
        if hit is not None:
            self._cache.move_to_end(cc)
            return hit
        produced = self._gen(chunk_seed(self._layout.seed, cc), cc, self._layout.cell(cc))
        self._cache[cc] = produced
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)   # evict LRU -> bounded memory
        return produced

    @staticmethod
    def _split(pos: Coord) -> tuple[ChunkCoord, Coord]:
        x, y = pos
        return (x // CHUNK, y // CHUNK), (x % CHUNK, y % CHUNK)

    def is_wall(self, pos: Coord) -> bool:
        cc, (lx, ly) = self._split(pos)
        return self.chunk(cc).grid.is_wall(lx, ly)

    def static_block_at(self, pos: Coord) -> bool:
        """A statically blocking object (e.g. Table) on the cell.

        Doors are *not* treated as static blockers here: their locked/open state is
        runtime, so the navigator passes locked-door tiles via its ``blocked`` set.
        """
        cc, _ = self._split(pos)
        for obj in self.chunk(cc).objects:
            if obj.pos == pos and obj.type in BLOCKING_TYPES and obj.type is not EntityType.DOOR:
                return True
        return False

    def passable(self, pos: Coord) -> bool:
        return not self.is_wall(pos) and not self.static_block_at(pos)

    def neighbors(self, pos: Coord) -> Iterator[Coord]:
        """4-connected passable neighbors — the only graph primitive BFS/A* need."""
        x, y = pos
        for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if self.passable(nxt):
                yield nxt
