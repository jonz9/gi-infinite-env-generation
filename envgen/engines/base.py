"""Engines / renderers — frozen registry (Stage 6).

⚠️ FROZEN FILE. Do not edit as part of a ticket. Every renderer consumes the *same*
scene-graph IR (engine-independence invariant): ASCII now, PyGame/image later, the
same JSON in. Tickets add renderers under ``engines/renderers/`` (self-registering);
the Phase-0 ASCII renderer in :mod:`envgen.render` is untouched. See ``tickets/README.md``.
"""
from __future__ import annotations

from typing import Callable, Union

from envgen.schema import SceneGraph

# A renderer turns a scene into text (ASCII) or bytes (PNG/surface dump).
Renderer = Callable[[SceneGraph], Union[str, bytes]]

_RENDERERS: dict[str, Renderer] = {}


def register_renderer(name: str, renderer: Renderer) -> Renderer:
    """Register a renderer under ``name``. Raises on duplicate names."""
    if name in _RENDERERS and _RENDERERS[name] is not renderer:
        raise ValueError(f"renderer {name!r} already registered")
    _RENDERERS[name] = renderer
    return renderer


def get_renderer(name: str) -> Renderer:
    _discover()
    if name not in _RENDERERS:
        valid = ", ".join(sorted(_RENDERERS)) or "(none)"
        raise KeyError(f"unknown renderer {name!r}; registered: {valid}")
    return _RENDERERS[name]


def registered_renderers() -> dict[str, Renderer]:
    _discover()
    return dict(_RENDERERS)


def _discover() -> None:
    from envgen.engines import renderers as _r  # noqa: F401
