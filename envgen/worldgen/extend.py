"""``Extend`` macro-op — infinite generation as a single edit (Stage 4, ticket S4-T04).

The literal realization of the architecture's "make more world = one op". ``Extend``
authors a band of ``n`` new :class:`~envgen.infinite.MacroCell`s beyond the current
layout's bounding box in a cardinal direction, each carrying a chosen biome. It is a
*pure transform*: it never mutates its input — it clones the layout and returns the
grown one — so the macro op-log ``seed + [op...]`` deterministically reproduces the
world (the determinism invariant). Round-trips through ``to_dict``/``from_dict`` as
plain JSON, the only handoff.

Note: like ``SetBiome`` this acts on the *macro layer* (``MacroLayout``), not the
frozen ``SceneGraph`` ``EditOp`` contract — that is the Stage-4 design decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from envgen.infinite import ChunkCoord, MacroCell, MacroLayout

DIRECTIONS = ("N", "S", "E", "W")


def _bbox(cells: dict[ChunkCoord, MacroCell]) -> tuple[int, int, int, int]:
    """(xmin, ymin, xmax, ymax) over authored cells; origin box when empty."""
    if not cells:
        return (0, 0, 0, 0)
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return min(xs), min(ys), max(xs), max(ys)


@dataclass(frozen=True)
class Extend:
    """Grow a layout by ``n`` chunks of ``biome`` in ``direction`` (one of N/S/E/W)."""

    direction: str
    n: int
    biome: str

    def __post_init__(self) -> None:
        if self.direction not in DIRECTIONS:
            raise ValueError(f"direction must be one of {DIRECTIONS}, got {self.direction!r}")
        if self.n <= 0:
            raise ValueError(f"n must be positive, got {self.n}")

    def new_coords(self, layout: MacroLayout) -> list[ChunkCoord]:
        """The chunk coords this op would author onto ``layout`` (frontier band)."""
        xmin, ymin, xmax, ymax = _bbox(layout.cells)
        band = range(1, self.n + 1)
        if self.direction == "E":
            return [(xmax + i, cy) for i in band for cy in range(ymin, ymax + 1)]
        if self.direction == "W":
            return [(xmin - i, cy) for i in band for cy in range(ymin, ymax + 1)]
        if self.direction == "S":
            return [(cx, ymax + i) for i in band for cx in range(xmin, xmax + 1)]
        return [(cx, ymin - i) for i in band for cx in range(xmin, xmax + 1)]  # "N"

    def affected_chunks(self, layout: MacroLayout) -> set[ChunkCoord]:
        """Chunks whose content changes (were ``fill_biome``, now authored)."""
        return set(self.new_coords(layout))

    def apply(self, layout: MacroLayout) -> MacroLayout:
        """Return a clone of ``layout`` with the frontier band authored (input intact)."""
        cells = dict(layout.cells)
        for cc in self.new_coords(layout):
            cells.setdefault(cc, MacroCell(biome=self.biome))
        return MacroLayout(
            seed=layout.seed, cells=cells, goal=layout.goal, fill_biome=layout.fill_biome
        )

    def to_dict(self) -> dict[str, Any]:
        return {"op": "Extend", "direction": self.direction, "n": self.n, "biome": self.biome}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Extend":
        if data.get("op") != "Extend":
            raise ValueError(f"not an Extend op: {data.get('op')!r}")
        return cls(direction=data["direction"], n=int(data["n"]), biome=data["biome"])
