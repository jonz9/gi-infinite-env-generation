"""Ice — a slippery but passable tile (Stage 4, ticket S4-T18).

Ice is traversable (not a hazard, not a static blocker); its distinguishing trait
is ``slide`` momentum for a future continuous/engine renderer. For grid solvability
it behaves like floor, so the lazy validator/solver walk across it normally. Carried
as an :class:`EntityKind` so renderers/engines can special-case its glyph + physics.
"""
from __future__ import annotations

from envgen.entities.registry import EntityKind, register_kind

# Ice slides but never blocks or kills — passable floor with a distinct glyph.
register_kind(EntityKind(name="Ice", glyph="*", blocks_move=False, is_hazard=False))
