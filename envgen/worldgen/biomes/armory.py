"""Armory biome — the puzzle region (Stage 4, ticket S4-T10).

A dungeon-style ``rooms`` region whose macro cells carry the Key/Door/Exit puzzle
objects. Terrain (rooms + corridors) is the micro layer; the semantic objects are
authored on the ``MacroCell`` by the macro (LLM) layer and attached to chunks by the
:mod:`envgen.worldgen.build` dispatcher — so the armory needs no custom chunkgen, only
to declare that ``rooms`` paints it. This is the biome where lock-and-key challenges
live.
"""
from __future__ import annotations

from envgen.worldgen.base import Biome, register_biome

register_biome(Biome(
    name="armory",
    chunkgen="rooms",
    description="dungeon rooms seeded with Key/Door/Exit puzzles (macro-authored objects)",
))
