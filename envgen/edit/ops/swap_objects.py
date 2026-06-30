"""SwapObjects — exchange the grid positions of two existing objects.

Self-registering :class:`~envgen.edit.base.EditOp` under the ``"SwapObjects"``
key. Swaps the positions of the objects named ``a`` and ``b``, rejecting (with a
specific :class:`~envgen.edit.base.EditError`) an unknown id, the same id given
twice, or a swap that would produce an illegal placement — a blocking object
(Table/Door, see ``envgen/validate.py``) landing on a wall tile or on a cell
occupied by another object. Application is pure: the result is built from
``clone_scene(scene)`` so the input is never mutated.

The op is its own :meth:`inverse` — swapping the same two ids back returns the
original scene (an involution).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from envgen.edit.base import EditError, EditOp, clone_scene, register_op
from envgen.schema import BLOCKING_TYPES, SceneGraph, SceneObject


@register_op
@dataclass
class SwapObjects(EditOp):
    """Swap the grid positions of objects ``a`` and ``b``."""

    op = "SwapObjects"

    a: str
    b: str

    def apply(self, scene: SceneGraph) -> SceneGraph:
        if self.a == self.b:
            raise EditError(
                f"SwapObjects: cannot swap an object with itself ({self.a!r})"
            )
        result = clone_scene(scene)
        obj_a = result.get(self.a)
        obj_b = result.get(self.b)
        if obj_a is None:
            raise EditError(f"SwapObjects: unknown object id {self.a!r}")
        if obj_b is None:
            raise EditError(f"SwapObjects: unknown object id {self.b!r}")

        pos_a, pos_b = obj_a.pos, obj_b.pos
        obj_a.pos, obj_b.pos = pos_b, pos_a

        # Validate the two moved objects at their new cells. They cannot collide
        # with each other (each took the other's vacated cell), so check only
        # against the *other* objects.
        for moved in (obj_a, obj_b):
            self._check_placement(result, moved)
        return result

    @staticmethod
    def _check_placement(scene: SceneGraph, moved: SceneObject) -> None:
        """Reject a wall tile or a blocking-rule collision for ``moved``'s new cell."""
        x, y = moved.pos
        if scene.grid.is_wall(x, y):
            raise EditError(
                f"SwapObjects: {moved.id!r} would land on a wall tile at ({x},{y})"
            )
        moved_blocks = moved.type in BLOCKING_TYPES
        for other in scene.objects:
            if other.id == moved.id:
                continue
            if tuple(other.pos) != (x, y):
                continue
            if moved_blocks or other.type in BLOCKING_TYPES:
                raise EditError(
                    f"SwapObjects: {moved.id!r} would land on ({x},{y}), "
                    f"overlapping blocking object {other.id!r}"
                )

    def inverse(self, scene: SceneGraph) -> "SwapObjects":
        # Swapping the same two ids back undoes the swap (involution).
        return SwapObjects(a=self.a, b=self.b)

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, "a": self.a, "b": self.b}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SwapObjects":
        for key in ("a", "b"):
            if key not in data:
                raise EditError(f"SwapObjects: missing required field {key!r}: {data!r}")
        return cls(a=str(data["a"]), b=str(data["b"]))
