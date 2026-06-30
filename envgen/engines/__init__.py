"""Engines / renderers subsystem (Stage 6).

Frozen surface: the renderer registry in :mod:`envgen.engines.base`. Concrete
renderers live one-per-file under :mod:`.renderers` and are discovered automatically.
"""
from envgen.engines.base import (
    Renderer,
    get_renderer,
    register_renderer,
    registered_renderers,
)

__all__ = ["Renderer", "get_renderer", "register_renderer", "registered_renderers"]
