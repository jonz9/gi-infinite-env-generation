"""Entity-extension subsystem — register new object/tile kinds out-of-tree.

Frozen surface: :class:`EntityKind`, :func:`register_kind`, :func:`get_kind`,
:func:`registered_kinds`. Concrete kinds live one-per-file under
:mod:`envgen.entities.kinds` and are discovered automatically.
"""
from envgen.entities.registry import (
    EntityKind,
    get_kind,
    register_kind,
    registered_kinds,
)

__all__ = ["EntityKind", "get_kind", "register_kind", "registered_kinds"]
