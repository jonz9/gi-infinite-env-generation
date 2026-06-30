"""Infinite world generation — frozen registries for chunk generators & biomes.

⚠️ FROZEN FILE. Do not edit as part of a ticket. Builds on :mod:`envgen.infinite`
(the ``world(seed, x, y) -> tile`` substrate). Tickets add chunk generators under
``worldgen/chunkgens/`` and biomes under ``worldgen/biomes/``, each self-registering,
so this file and the package ``__init__``s never change. See ``tickets/README.md``.

A **chunk generator** is the deterministic micro layer: ``(chunk_seed, chunk_coord,
macro_cell|None) -> Chunk`` (see :data:`envgen.infinite.ChunkGen`). A **biome** is a
macro-layer descriptor: which chunk generator paints a region plus how semantic
objects are populated into it.
"""
from __future__ import annotations

from dataclasses import dataclass

from envgen.infinite import ChunkGen


@dataclass(frozen=True)
class Biome:
    """Macro-layer descriptor: a named region style.

    Attributes
    ----------
    name: registry key + the ``MacroCell.biome`` string (e.g. ``"armory"``).
    chunkgen: registry name of the :data:`~envgen.infinite.ChunkGen` that paints it.
    description: one-line human summary (for prompts / docs).
    """

    name: str
    chunkgen: str
    description: str = ""


# --- chunk-generator registry -------------------------------------------------
_CHUNKGENS: dict[str, ChunkGen] = {}


def register_chunkgen(name: str, gen: ChunkGen) -> ChunkGen:
    """Register a chunk generator under ``name``. Raises on duplicate names."""
    if name in _CHUNKGENS and _CHUNKGENS[name] is not gen:
        raise ValueError(f"chunkgen {name!r} already registered")
    _CHUNKGENS[name] = gen
    return gen


def get_chunkgen(name: str) -> ChunkGen:
    """Look up a registered chunk generator (triggers discovery)."""
    _discover()
    if name not in _CHUNKGENS:
        valid = ", ".join(sorted(_CHUNKGENS)) or "(none)"
        raise KeyError(f"unknown chunkgen {name!r}; registered: {valid}")
    return _CHUNKGENS[name]


def registered_chunkgens() -> dict[str, ChunkGen]:
    _discover()
    return dict(_CHUNKGENS)


# --- biome registry -----------------------------------------------------------
_BIOMES: dict[str, Biome] = {}


def register_biome(biome: Biome) -> Biome:
    """Register a :class:`Biome`. Raises on duplicate names."""
    if biome.name in _BIOMES and _BIOMES[biome.name] != biome:
        raise ValueError(f"biome {biome.name!r} already registered")
    _BIOMES[biome.name] = biome
    return biome


def get_biome(name: str) -> Biome:
    _discover()
    if name not in _BIOMES:
        valid = ", ".join(sorted(_BIOMES)) or "(none)"
        raise KeyError(f"unknown biome {name!r}; registered: {valid}")
    return _BIOMES[name]


def registered_biomes() -> dict[str, Biome]:
    _discover()
    return dict(_BIOMES)


def _discover() -> None:
    """Import the chunkgen + biome packages so their modules self-register."""
    from envgen.worldgen import biomes as _b  # noqa: F401
    from envgen.worldgen import chunkgens as _c  # noqa: F401
