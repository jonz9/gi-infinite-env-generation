"""``AddObject`` edit op — place a new :class:`~envgen.schema.SceneObject`.

Self-registers via :func:`~envgen.edit.base.register_op`; dropped into
``envgen/edit/ops/`` and auto-discovered. No import-time side effects beyond the
class definition + registration. See ``tickets/README.md`` and the S1-T01 ticket.

Inverse choice
--------------
The structural inverse of ``AddObject`` is ``RemoveObject(id)``. ``RemoveObject``
lives in a *separate* op module (ticket S1-T02), so importing it here would create
an import-time cross-ticket dependency. Instead :meth:`inverse` constructs the
inverse *lazily* through :func:`~envgen.edit.base.op_from_dict` — purely by op key,
resolved at call time against the live registry. If ``RemoveObject`` is not yet
registered, ``op_from_dict`` raises a specific :class:`EditError`.
"""
from __future__ import annotations

from typing import Any

from envgen.edit.base import EditError, EditOp, clone_scene, op_from_dict, register_op
from envgen.schema import BLOCKING_TYPES, EntityType, SceneGraph, SceneObject


@register_op
class AddObject(EditOp):
    """Add one object (``type`` at ``pos``, optional ``opens``/``locked``).

    ``id`` may be supplied by the caller or auto-generated (``<type><n>``) so it is
    unique within the scene. Application is pure: it builds from ``clone_scene`` and
    never mutates the input.
    """

    op = "AddObject"

    def __init__(
        self,
        type: EntityType | str,
        pos: tuple[int, int] | list[int],
        *,
        id: str | None = None,
        opens: str | None = None,
        locked: bool = False,
    ) -> None:
        self.obj_type = type if isinstance(type, EntityType) else EntityType(type)
        self.pos: tuple[int, int] = (int(pos[0]), int(pos[1]))
        self.obj_id = id
        self.opens = opens
        self.locked = bool(locked)

    # -- application -------------------------------------------------------
    def apply(self, scene: SceneGraph) -> SceneGraph:
        new = clone_scene(scene)
        obj_id = self.obj_id or self._auto_id(new)
        x, y = self.pos
        if new.get(obj_id) is not None:
            raise EditError(f"AddObject: duplicate object id {obj_id!r}")
        if not new.grid.in_bounds(x, y):
            raise EditError(
                f"AddObject: pos ({x},{y}) out of bounds for "
                f"{new.grid.w}x{new.grid.h} grid"
            )
        if new.grid.is_wall(x, y):
            raise EditError(f"AddObject: pos ({x},{y}) is on a wall tile")
        self._check_stackability(new)
        new.objects.append(
            SceneObject(
                id=obj_id,
                type=self.obj_type,
                pos=self.pos,
                opens=self.opens,
                locked=self.locked,
            )
        )
        return new

    def _check_stackability(self, scene: SceneGraph) -> None:
        """Blocking types (Table/Door) must occupy their cell exclusively."""
        new_blocks = self.obj_type in BLOCKING_TYPES
        for other in scene.objects:
            if other.pos != self.pos:
                continue
            if new_blocks or other.type in BLOCKING_TYPES:
                raise EditError(
                    f"AddObject: {self.obj_type.value} at "
                    f"({self.pos[0]},{self.pos[1]}) overlaps blocking object "
                    f"{other.id!r} (blocking types must be exclusive)"
                )

    def _auto_id(self, scene: SceneGraph) -> str:
        """Deterministic ``<type><n>`` id, unique within ``scene``."""
        base = self.obj_type.value.lower()
        existing = {o.id for o in scene.objects}
        n = 1
        while f"{base}{n}" in existing:
            n += 1
        return f"{base}{n}"

    # -- inverse -----------------------------------------------------------
    def inverse(self, scene: SceneGraph) -> EditOp:
        """``RemoveObject(id)`` built lazily by op key (no import-time dependency)."""
        obj_id = self.obj_id or self._auto_id(scene)
        return op_from_dict({"op": "RemoveObject", "id": obj_id})

    # -- (de)serialization -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "op": self.op,
            "type": self.obj_type.value,
            "pos": [self.pos[0], self.pos[1]],
        }
        if self.obj_id is not None:
            data["id"] = self.obj_id
        if self.opens is not None:
            data["opens"] = self.opens
        if self.obj_type is EntityType.DOOR:
            data["locked"] = self.locked
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AddObject":
        for key in ("type", "pos"):
            if key not in data:
                raise EditError(f"AddObject dict missing required field {key!r}: {data!r}")
        try:
            etype = EntityType(data["type"])
        except ValueError as exc:
            valid = ", ".join(t.value for t in EntityType)
            raise EditError(
                f"AddObject: unknown type {data['type']!r}; valid: {valid}"
            ) from exc
        pos = data["pos"]
        if not (isinstance(pos, (list, tuple)) and len(pos) == 2):
            raise EditError(f"AddObject: pos must be [x, y], got {pos!r}")
        return cls(
            etype,
            (int(pos[0]), int(pos[1])),
            id=data.get("id"),
            opens=data.get("opens"),
            locked=bool(data.get("locked", False)),
        )

    # -- equality / repr (so round-trip equality holds) --------------------
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AddObject):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        return (
            f"AddObject(type={self.obj_type.value!r}, pos={self.pos}, "
            f"id={self.obj_id!r}, opens={self.opens!r}, locked={self.locked})"
        )
