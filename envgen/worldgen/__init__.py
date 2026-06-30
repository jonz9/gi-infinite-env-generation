"""Infinite world-generation subsystem (Stage 4).

Frozen surface: the registries in :mod:`envgen.worldgen.base`
(:func:`register_chunkgen`/:func:`get_chunkgen`/:func:`registered_chunkgens`,
:func:`register_biome`/:func:`get_biome`/:func:`registered_biomes`, :class:`Biome`).
Concrete chunk generators and biomes live one-per-file under :mod:`.chunkgens` and
:mod:`.biomes` and are discovered automatically. Session/solver adapters that wire
:class:`~envgen.infinite.InfiniteWorld` into the harness are added by Stage 4 tickets
as their own modules.
"""
from envgen.worldgen.base import (
    Biome,
    get_biome,
    get_chunkgen,
    register_biome,
    register_chunkgen,
    registered_biomes,
    registered_chunkgens,
)

__all__ = [
    "Biome",
    "get_biome",
    "get_chunkgen",
    "register_biome",
    "register_chunkgen",
    "registered_biomes",
    "registered_chunkgens",
]
