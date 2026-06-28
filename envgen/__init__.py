"""envgen — natural language to playable 2D environments.

The scene graph (see :mod:`envgen.schema`) is the engine-independent IR that
every other module reads or writes.
"""

from envgen.env import Action, GridEnv
from envgen.planner import plan
from envgen.render import render, render_scene
from envgen.repair import Attempt, RepairError, plan_valid
from envgen.schema import (
    BLOCKING_TYPES,
    EntityType,
    Grid,
    SceneGraph,
    SceneObject,
    SchemaError,
    check_well_formed,
)
from envgen.solve import SolveResult, solve
from envgen.validate import ValidationReport, validate
from envgen.world import World

__all__ = [
    "BLOCKING_TYPES",
    "Action",
    "Attempt",
    "EntityType",
    "Grid",
    "GridEnv",
    "RepairError",
    "SceneGraph",
    "SceneObject",
    "SchemaError",
    "SolveResult",
    "ValidationReport",
    "World",
    "check_well_formed",
    "plan",
    "plan_valid",
    "render",
    "render_scene",
    "solve",
    "validate",
]
