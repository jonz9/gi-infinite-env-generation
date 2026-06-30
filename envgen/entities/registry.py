"""Entity-extension registry — add new object/tile kinds without editing schema.py.

⚠️ FROZEN FILE. Do not edit as part of a ticket. The five core types (Player, Table,
Key, Door, Exit) stay in :mod:`envgen.schema` for Phase-0 compatibility. NEW kinds
(Lava, Water, PushBlock, Ice, ...) register here, one-per-file under
``envgen/entities/kinds/``, so the core enum and frozen Phase-0 code never change.

New renderers/engines/worldgen consult this registry for glyphs and movement
semantics; the original ASCII renderer and finite validator keep handling only the
core types. See ``tickets/README.md``.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityKind:
    """Declarative description of an extended entity/tile kind.

    Attributes
    ----------
    name: registry key + scene-graph ``type`` string (e.g. ``"Lava"``).
    glyph: single char for ASCII rendering.
    blocks_move: True if standing on it is impossible (a static wall-like blocker).
    is_hazard: True if entering the cell fails/kills the run (e.g. Lava) — used by
        the env's code-level objective, never a pixel check.
    pushable: True if the player can push it one cell (e.g. PushBlock).
    """

    name: str
    glyph: str
    blocks_move: bool = False
    is_hazard: bool = False
    pushable: bool = False


_KINDS: dict[str, EntityKind] = {}


def register_kind(kind: EntityKind) -> EntityKind:
    """Register an :class:`EntityKind`. Raises on a duplicate name (no silent clobber)."""
    if kind.name in _KINDS and _KINDS[kind.name] != kind:
        raise ValueError(f"entity kind {kind.name!r} already registered")
    _KINDS[kind.name] = kind
    return kind


def get_kind(name: str) -> EntityKind | None:
    """Look up an extended kind by name, or None if it is a core type / unknown."""
    _discover()
    return _KINDS.get(name)


def registered_kinds() -> dict[str, EntityKind]:
    """A copy of all registered extended kinds (triggers discovery)."""
    _discover()
    return dict(_KINDS)


def _discover() -> None:
    """Import the kinds package so each kind module self-registers."""
    from envgen.entities import kinds as _kinds  # noqa: F401
