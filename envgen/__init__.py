"""envgen — natural language to playable 2D environments.

The scene graph (see :mod:`envgen.schema`) is the engine-independent IR that
every other module reads or writes.
"""

from envgen.render import render, render_scene
from envgen.schema import (
    BLOCKING_TYPES,
    EntityType,
    Grid,
    SceneGraph,
    SceneObject,
    SchemaError,
    check_well_formed,
)
from envgen.world import World

__all__ = [
    "BLOCKING_TYPES",
    "EntityType",
    "Grid",
    "SceneGraph",
    "SceneObject",
    "SchemaError",
    "World",
    "check_well_formed",
    "render",
    "render_scene",
]
