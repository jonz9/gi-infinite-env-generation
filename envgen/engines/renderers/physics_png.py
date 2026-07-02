"""Registered ``physics_png`` renderer — a scene's initial physics state as PNG bytes.

Slots the Box2D view into the frozen renderer registry: same JSON scene in, PNG
bytes out. Box2D is imported lazily inside the call so registry discovery never
fails when the extra isn't installed.
"""
from __future__ import annotations

from envgen.engines.base import register_renderer
from envgen.schema import SceneGraph


def physics_png(scene: SceneGraph) -> bytes:
    from envgen.engines.box2d_engine import PhysicsWorld
    from envgen.engines.play import render_physics_frame
    from envgen.pixels import to_png_bytes

    return to_png_bytes(render_physics_frame(PhysicsWorld(scene)))


register_renderer("physics_png", physics_png)
