"""``CloneObject`` edit op — duplicate an existing object to a new position.

One verb of the edit algebra (see ``tickets/stage-1-edit-algebra.md``, S1-T09).
Self-registers via :func:`~envgen.edit.base.register_op`; dropped into
``envgen/edit/ops/`` and auto-discovered. No import-time side effects beyond the
class definition + registration.

Behaviour
---------
Look up the source object by ``id``, copy its properties (``type``/``opens``/
``locked``), and place the copy at ``to=[x,y]`` under a *fresh* unique id. The
clone undergoes the same placement validation as ``AddObject``: the target must be
in bounds, on a floor tile, and respect the stackability rule (blocking Table/Door
cells are exclusive). The new id must not collide with an existing object.

Inverse choice
--------------
The structural inverse of ``CloneObject`` is ``RemoveObject(new_id)`` — deleting
the clone restores the pre-state. ``RemoveObject`` lives in a *separate* op module
(S1-T02), so :meth:`inverse` constructs it *lazily* through
:func:`~envgen.edit.base.op_from_dict` — purely by op key, resolved at call time
against the live registry — to avoid an import-time cross-ticket dependency.
"""
from __future__ import annotations

from typing import Any

from envgen.edit.base import EditError, EditOp, clone_scene, op_from_dict, register_op
from envgen.schema import BLOCKING_TYPES, SceneGraph, SceneObject


@register_op
class CloneObject(EditOp):
    """Duplicate object ``id`` to ``to=[x,y]`` with a fresh unique ``new_id``.

    ``new_id`` may be supplied by the caller or auto-generated (``<sourceid>_copy``,
    ``<sourceid>_copy2``, ...) so it is unique within the scene. Application is
    pure: it builds from ``clone_scene`` and never mutates the input.
    """

    op = "CloneObject"

    def __init__(
        self,
        id: str,
        to: tuple[int, int] | list[int],
        *,
        new_id: str | None = None,
    ) -> None:
        self.id = str(id)
        self.to: tuple[int, int] = (int(to[0]), int(to[1]))
        self.new_id = new_id

    # -- application -------------------------------------------------------
    def apply(self, scene: SceneGraph) -> SceneGraph:
        new = clone_scene(scene)
        source = new.get(self.id)
        if source is None:
            raise EditError(
                f"CloneObject: no source object with id {self.id!r} in scene "
                f"(have: {', '.join(o.id for o in new.objects) or '(none)'})"
            )
        clone_id = self.new_id or self._auto_id(new)
        x, y = self.to
        if new.get(clone_id) is not None:
            raise EditError(f"CloneObject: new id {clone_id!r} collides with existing object")
        if not new.grid.in_bounds(x, y):
            raise EditError(
                f"CloneObject: target ({x},{y}) out of bounds for "
                f"{new.grid.w}x{new.grid.h} grid"
            )
        if new.grid.is_wall(x, y):
            raise EditError(f"CloneObject: target ({x},{y}) is on a wall tile")
        self._check_stackability(new, source)
        new.objects.append(
            SceneObject(
                id=clone_id,
                type=source.type,
                pos=self.to,
                opens=source.opens,
                locked=source.locked,
            )
        )
        return new

    def _check_stackability(self, scene: SceneGraph, source: SceneObject) -> None:
        """Blocking types (Table/Door) must occupy their cell exclusively."""
        new_blocks = source.type in BLOCKING_TYPES
        for other in scene.objects:
            if other.pos != self.to:
                continue
            if new_blocks or other.type in BLOCKING_TYPES:
                raise EditError(
                    f"CloneObject: {source.type.value} clone at "
                    f"({self.to[0]},{self.to[1]}) overlaps blocking object "
                    f"{other.id!r} (blocking types must be exclusive)"
                )

    def _auto_id(self, scene: SceneGraph) -> str:
        """Deterministic ``<sourceid>_copy[n]`` id, unique within ``scene``."""
        existing = {o.id for o in scene.objects}
        candidate = f"{self.id}_copy"
        if candidate not in existing:
            return candidate
        n = 2
        while f"{self.id}_copy{n}" in existing:
            n += 1
        return f"{self.id}_copy{n}"

    # -- inverse -----------------------------------------------------------
    def inverse(self, scene: SceneGraph) -> EditOp:
        """``RemoveObject(new_id)`` built lazily by op key (no import-time dep)."""
        clone_id = self.new_id or self._auto_id(scene)
        return op_from_dict({"op": "RemoveObject", "id": clone_id})

    # -- (de)serialization -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "op": self.op,
            "id": self.id,
            "to": [self.to[0], self.to[1]],
        }
        if self.new_id is not None:
            data["new_id"] = self.new_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CloneObject":
        for key in ("id", "to"):
            if key not in data:
                raise EditError(f"CloneObject dict missing required field {key!r}: {data!r}")
        to = data["to"]
        if not (isinstance(to, (list, tuple)) and len(to) == 2):
            raise EditError(f"CloneObject: to must be [x, y], got {to!r}")
        return cls(
            id=str(data["id"]),
            to=(int(to[0]), int(to[1])),
            new_id=data.get("new_id"),
        )

    # -- equality / repr (so round-trip equality holds) --------------------
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CloneObject):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        return f"CloneObject(id={self.id!r}, to={self.to}, new_id={self.new_id!r})"
