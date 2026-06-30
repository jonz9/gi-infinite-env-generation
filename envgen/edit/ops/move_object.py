"""MoveObject — relocate an existing object to a new grid cell.

Self-registering :class:`~envgen.edit.base.EditOp` under the ``"MoveObject"`` key.
Moves the object with ``id`` to ``to = [x, y]``, rejecting (with a specific
:class:`~envgen.edit.base.EditError`) an unknown id, an out-of-bounds target, a
target on a wall tile, or a target that would violate the stackability rule
(blocking objects — Table/Door — must occupy their cell exclusively; see
``envgen/validate.py``). Application is pure: the result is built from
``clone_scene(scene)`` so the input is never mutated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from envgen.edit.base import EditError, EditOp, clone_scene, register_op
from envgen.schema import BLOCKING_TYPES, SceneGraph


@register_op
@dataclass
class MoveObject(EditOp):
    """Move object ``id`` to grid cell ``to`` (``[x, y]``)."""

    op = "MoveObject"

    id: str
    to: tuple[int, int]

    def apply(self, scene: SceneGraph) -> SceneGraph:
        result = clone_scene(scene)
        obj = result.get(self.id)
        if obj is None:
            raise EditError(f"MoveObject: unknown object id {self.id!r}")

        x, y = self.to
        if not result.grid.in_bounds(x, y):
            raise EditError(
                f"MoveObject: target ({x},{y}) for {self.id!r} is out of bounds "
                f"(grid is {result.grid.w}x{result.grid.h})"
            )
        if result.grid.is_wall(x, y):
            raise EditError(
                f"MoveObject: target ({x},{y}) for {self.id!r} is on a wall tile"
            )

        moved_blocks = obj.type in BLOCKING_TYPES
        for other in result.objects:
            if other.id == self.id:
                continue
            if tuple(other.pos) != (x, y):
                continue
            if moved_blocks or other.type in BLOCKING_TYPES:
                raise EditError(
                    f"MoveObject: target ({x},{y}) for {self.id!r} overlaps "
                    f"blocking object {other.id!r}"
                )

        obj.pos = (x, y)
        return result

    def inverse(self, scene: SceneGraph) -> "MoveObject":
        obj = scene.get(self.id)
        if obj is None:
            raise EditError(
                f"MoveObject.inverse: unknown object id {self.id!r} in pre-state"
            )
        return MoveObject(id=self.id, to=(obj.pos[0], obj.pos[1]))

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, "id": self.id, "to": [self.to[0], self.to[1]]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MoveObject":
        for key in ("id", "to"):
            if key not in data:
                raise EditError(f"MoveObject: missing required field {key!r}: {data!r}")
        to = data["to"]
        if not (isinstance(to, (list, tuple)) and len(to) == 2):
            raise EditError(f"MoveObject: 'to' must be [x, y], got {to!r}")
        return cls(id=str(data["id"]), to=(int(to[0]), int(to[1])))
