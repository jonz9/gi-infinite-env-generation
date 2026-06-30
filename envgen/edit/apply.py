"""Pure helpers to apply one op or a sequence of ops to a scene.

⚠️ FROZEN FILE. Do not edit as part of a ticket. These are thin, registry-driven
helpers; op *behavior* lives in the individual op modules under ``ops/``.
"""
from __future__ import annotations

from typing import Iterable

from envgen.edit.base import EditOp, op_from_dict
from envgen.schema import SceneGraph


def apply_op(scene: SceneGraph, op: EditOp) -> SceneGraph:
    """Apply a single op, returning a new scene (the input is left untouched)."""
    return op.apply(scene)


def apply_ops(scene: SceneGraph, ops: Iterable[EditOp]) -> SceneGraph:
    """Fold a sequence of ops over a scene. Raises on the first op that fails."""
    result = scene
    for op in ops:
        result = op.apply(result)
    return result


def ops_from_dicts(items: Iterable[dict]) -> list[EditOp]:
    """Parse a list of op dicts (e.g. a compiler's JSON output) into ops."""
    return [op_from_dict(item) for item in items]
