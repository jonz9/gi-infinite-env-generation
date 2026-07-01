"""InfiniteSession — the changing, infinite world as a persistent session (S4-T03).

The Stage-4 analogue of the Stage-2 :class:`~envgen.session.core.HarnessSession`: a
live :class:`~envgen.infinite.MacroLayout` + :class:`~envgen.infinite.InfiniteWorld`
that an agent grows and repaints by applying **macro ops** (``Extend`` / ``SetBiome``),
while it stays provably solvable whenever a full puzzle is authored. It reuses the
Stage-2 op-log machinery (:class:`~envgen.session.oplog.OpLog` /
:class:`~envgen.session.base.OpLogEntry`): the macro op-log — pure JSON — plus the
initial layout reproduces the exact world (the determinism invariant), verified by
:meth:`determinism_check`.

Windows onto the live world are materialized with :func:`envgen.worldgen.window.window`,
so the finite render/validate/solve toolchain applies to any visible slice.

Cache note: macro ops mutate the layout in place and evict *only* the chunks they
affect, so a growing world keeps its warm cache. ``InfiniteWorld`` exposes no public
invalidation hook, so eviction reaches its cache through a small guarded helper — a
candidate for a public method in a later pass (see handoff integration flags).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Sequence, Union

from envgen.infinite import CHUNK, ChunkCoord, InfiniteWorld, MacroCell, MacroLayout
from envgen.schema import EntityType, SceneGraph
from envgen.session.base import OpLogEntry
from envgen.session.oplog import OpLog
from envgen.worldgen.build import build_world
from envgen.worldgen.extend import Extend
from envgen.worldgen.lazy_validate import lazy_validate
from envgen.worldgen.set_biome_op import SetBiome
from envgen.worldgen.window import window

MacroOp = Union[Extend, SetBiome]


@dataclass(frozen=True)
class MacroStep:
    """Result of applying one macro op — what changed and whether it still holds."""

    op: dict[str, Any]
    accepted: bool
    solved: bool
    reason: str = ""
    layout_hash: str = ""


def _clone(layout: MacroLayout) -> MacroLayout:
    return MacroLayout(
        seed=layout.seed, cells=dict(layout.cells),
        goal=layout.goal, fill_biome=layout.fill_biome,
    )


def layout_hash(layout: MacroLayout) -> str:
    """Stable content hash of a macro layout — the determinism anchor."""
    payload = {
        "seed": layout.seed,
        "goal": layout.goal,
        "fill_biome": layout.fill_biome,
        "cells": [
            [list(cc), cell.biome, [o.to_dict() for o in cell.objects]]
            for cc, cell in sorted(layout.cells.items())
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode()).hexdigest()


def parse_macro_op(data: dict[str, Any]) -> MacroOp:
    """Rebuild a macro op from its ``to_dict`` form (op-log replay)."""
    tag = data.get("op")
    if tag == "Extend":
        return Extend.from_dict(data)
    if tag == "SetBiome":
        return SetBiome.from_dict(data)
    raise ValueError(f"unknown macro op {tag!r}")


def _evict(world: InfiniteWorld, ccs: set[ChunkCoord]) -> None:
    """Drop the named chunks from the world's warm cache (guarded private access)."""
    cache = getattr(world, "_cache", None)
    if cache is None:
        return
    for cc in ccs:
        cache.pop(cc, None)


class InfiniteSession:
    """A persistent, growing, provably-solvable infinite world."""

    def __init__(self, layout: MacroLayout | None = None, *, cache_size: int = 256) -> None:
        base = layout if layout is not None else MacroLayout(seed=0)
        self._initial = _clone(base)
        self._layout = _clone(base)
        self._world = build_world(self._layout, cache_size=cache_size)
        self._log = OpLog()

    # -- live surface -------------------------------------------------------
    @property
    def layout(self) -> MacroLayout:
        return self._layout

    @property
    def world(self) -> InfiniteWorld:
        return self._world

    @property
    def solved(self) -> bool:
        return self._solved()

    def window(self, x0: int, y0: int, w: int, h: int) -> SceneGraph:
        """A finite SceneGraph slice of the live world (render/validate/solve-ready)."""
        return window(self._world, x0, y0, w, h)

    def log(self) -> list[OpLogEntry]:
        return self._log.entries

    # -- editing ------------------------------------------------------------
    def step(self, ops: Sequence[MacroOp]) -> list[MacroStep]:
        """Apply macro ops in order, recording each in the op-log."""
        return [self.apply(op) for op in ops]

    def apply(self, op: MacroOp) -> MacroStep:
        """Apply one macro op: grow/repaint, keep solvability, log it.

        If the layout defines a complete puzzle (Player + Exit) the post-op world must
        stay solvable or the op is rolled back; a terrain-only world is always accepted.
        """
        affected = op.affected_chunks(self._layout)
        snapshot = _clone(self._layout)
        self._install(op.apply(self._layout), affected)

        solved = self._solved()
        if self._has_puzzle() and not solved:
            self._install(snapshot, affected)   # rollback
            entry = OpLogEntry(op=op.to_dict(), accepted=False,
                               reason="would break solvability")
            self._log.append(entry)
            return MacroStep(op.to_dict(), accepted=False, solved=self._solved(),
                             reason=entry.reason, layout_hash=layout_hash(self._layout))

        h = layout_hash(self._layout)
        self._log.append(OpLogEntry(op=op.to_dict(), accepted=True, scene_hash=h))
        return MacroStep(op.to_dict(), accepted=True, solved=solved, layout_hash=h)

    # -- determinism --------------------------------------------------------
    def determinism_check(self) -> bool:
        """Replay the accepted op-log from the initial layout; hashes must match."""
        replayed = InfiniteSession(self._initial)
        for entry in self._log:
            if entry.accepted:
                replayed.apply(parse_macro_op(entry.op))
        return layout_hash(replayed._layout) == layout_hash(self._layout)

    # -- internals ----------------------------------------------------------
    def _install(self, new_layout: MacroLayout, affected: set[ChunkCoord]) -> None:
        """Adopt ``new_layout`` in place (world reads it live) and evict stale chunks."""
        self._layout.cells.clear()
        self._layout.cells.update(new_layout.cells)
        self._layout.goal = new_layout.goal
        self._layout.fill_biome = new_layout.fill_biome
        _evict(self._world, affected)

    def _has_puzzle(self) -> bool:
        objs = self._layout.objects()
        types = {o.type for o in objs}
        return EntityType.PLAYER in types and EntityType.EXIT in types

    def _solved(self) -> bool:
        if not self._has_puzzle():
            return True
        ok, _ = lazy_validate(self._world)
        return ok
