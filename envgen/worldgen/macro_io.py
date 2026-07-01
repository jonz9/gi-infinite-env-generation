"""Macro-layout JSON I/O + authoring helpers (Stage 4, ticket S4-T16).

A :class:`~envgen.infinite.MacroLayout` is the LLM-authored, replayable artifact at the
top of the infinite substrate — this module makes it a first-class JSON document
(``layout_to_json`` / ``layout_from_json``, round-trip stable) plus a few *pure*
authoring builders (``place_region`` / ``set_goal`` / ``drop_object``) so a layout can
be assembled and versioned like any other IR. Every builder clones its input, matching
the macro-op discipline (see :mod:`envgen.worldgen.extend`).
"""
from __future__ import annotations

import json
from typing import Any

from envgen.infinite import ChunkCoord, MacroCell, MacroLayout
from envgen.schema import SceneObject


# -- (de)serialization ---------------------------------------------------------
def layout_to_dict(layout: MacroLayout) -> dict[str, Any]:
    """Plain-dict form; cells sorted for a canonical, diff-friendly document."""
    return {
        "seed": layout.seed,
        "goal": layout.goal,
        "fill_biome": layout.fill_biome,
        "cells": [
            {
                "cc": [cc[0], cc[1]],
                "biome": cell.biome,
                "objects": [o.to_dict() for o in cell.objects],
            }
            for cc, cell in sorted(layout.cells.items())
        ],
    }


def layout_from_dict(data: dict[str, Any]) -> MacroLayout:
    cells: dict[ChunkCoord, MacroCell] = {}
    for entry in data.get("cells", []):
        cc = (int(entry["cc"][0]), int(entry["cc"][1]))
        objects = tuple(SceneObject.from_dict(o) for o in entry.get("objects", []))
        cells[cc] = MacroCell(biome=entry["biome"], objects=objects)
    return MacroLayout(
        seed=int(data["seed"]),
        cells=cells,
        goal=data.get("goal", "reach exit"),
        fill_biome=data.get("fill_biome", "void"),
    )


def layout_to_json(layout: MacroLayout, *, indent: int | None = 2) -> str:
    return json.dumps(layout_to_dict(layout), indent=indent)


def layout_from_json(text: str) -> MacroLayout:
    return layout_from_dict(json.loads(text))


# -- pure authoring builders ---------------------------------------------------
def _clone(layout: MacroLayout) -> MacroLayout:
    return MacroLayout(
        seed=layout.seed, cells=dict(layout.cells),
        goal=layout.goal, fill_biome=layout.fill_biome,
    )


def place_region(
    layout: MacroLayout, biome: str, x0: int, y0: int, x1: int, y1: int
) -> MacroLayout:
    """Author every chunk in the inclusive rectangle with ``biome`` (objects kept)."""
    out = _clone(layout)
    for cy in range(min(y0, y1), max(y0, y1) + 1):
        for cx in range(min(x0, x1), max(x0, x1) + 1):
            existing = out.cells.get((cx, cy))
            objects = existing.objects if existing is not None else ()
            out.cells[(cx, cy)] = MacroCell(biome=biome, objects=objects)
    return out


def set_goal(layout: MacroLayout, goal: str) -> MacroLayout:
    """Return a clone with a new goal string."""
    out = _clone(layout)
    out.goal = goal
    return out


def drop_object(
    layout: MacroLayout, cc: ChunkCoord, obj: SceneObject, *, biome: str | None = None
) -> MacroLayout:
    """Add a semantic object to the cell at ``cc`` (authoring the cell if absent)."""
    out = _clone(layout)
    existing = out.cells.get(cc)
    cell_biome = biome or (existing.biome if existing else out.fill_biome)
    objects = (existing.objects if existing else ()) + (obj,)
    out.cells[cc] = MacroCell(biome=cell_biome, objects=objects)
    return out
