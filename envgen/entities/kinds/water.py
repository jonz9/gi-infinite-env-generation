"""Water — a hazard tile/object (Stage 4, ticket S4-T18).

Deep water is treated as a hazard: entering it fails/drowns the run, so the lazy
validator and solver route around it (via ``entities.get_kind("Water")``). Like
Lava it is not a static wall — the finite ``passable`` surface ignores it; hazard
semantics live only in the infinite-world consumers.
"""
from __future__ import annotations

from envgen.entities.registry import EntityKind, register_kind

register_kind(EntityKind(name="Water", glyph="~", blocks_move=False, is_hazard=True))
