"""Hazard-tile convention for the infinite substrate (Stage 4, T14/T15 support).

The frozen scene schema fixes the object vocabulary to five ``EntityType``s, so
hazards (Lava/Water — registered as :class:`~envgen.entities.EntityKind`, ticket
S4-T18) cannot ride as ``SceneObject``s. They live instead as **grid tile codes** on
a :class:`~envgen.infinite.Chunk`: ``0`` floor, ``1`` wall, and codes ``>=2`` mapping
to hazard kinds. ``Grid.is_wall`` only treats ``1`` as blocking, so a hazard tile is
"passable" to the frozen finite navigator but recognized here — the infinite-world
consumers (:mod:`envgen.worldgen.lazy_validate` / :mod:`.lazy_solve`) block hazardous
cells so proofs route around them. Semantics come from ``entities.get_kind``, never the
frozen finite env. (Finite windows collapse codes to 0/1, so hazards stay lazy-only.)
"""
from __future__ import annotations

from typing import Callable, Iterator

from envgen.entities import get_kind
from envgen.infinite import CHUNK, Coord, InfiniteWorld

#: grid tile code -> hazard EntityKind name. Extend alongside new hazard kinds.
HAZARD_CODES: dict[int, str] = {2: "Lava", 3: "Water"}

#: reverse map, for chunkgens/biomes painting hazard tiles by kind name.
CODE_FOR_KIND: dict[str, int] = {name: code for code, name in HAZARD_CODES.items()}


def tile_code(world: InfiniteWorld, pos: Coord) -> int:
    """Raw grid code at global ``pos`` (0 floor, 1 wall, >=2 hazard)."""
    x, y = pos
    cc = (x // CHUNK, y // CHUNK)
    lx, ly = x % CHUNK, y % CHUNK
    return world.chunk(cc).grid.tiles[ly][lx]


def is_hazard(world: InfiniteWorld, pos: Coord) -> bool:
    """True iff ``pos`` holds a hazard tile whose kind is lethal (``is_hazard``)."""
    name = HAZARD_CODES.get(tile_code(world, pos))
    if name is None:
        return False
    kind = get_kind(name)
    return bool(kind and kind.is_hazard)


def safe_neighbors(world: InfiniteWorld) -> Callable[[Coord], Iterator[Coord]]:
    """A ``neighbors`` callable that drops hazardous cells — drop-in for lazy_bfs.

    Wraps the frozen :meth:`InfiniteWorld.neighbors` (which already filters walls and
    static blockers) and additionally refuses to step onto a lethal hazard tile.
    """

    def neighbors(pos: Coord) -> Iterator[Coord]:
        for nxt in world.neighbors(pos):
            if not is_hazard(world, nxt):
                yield nxt

    return neighbors
