"""``SetProp`` — set a mutable property on an existing object.

Self-registering edit op (see ``envgen/edit/base.py``). Supports two properties:

* ``locked`` (Door only): ``bool`` — whether the door starts locked.
* ``opens`` (Key only): the id of the Door the key unlocks (or ``None`` to clear).

Anything else — an unknown target id, a prop that doesn't apply to the target's
type, or an ``opens`` value naming a non-Door / unknown id — raises a specific
:class:`~envgen.edit.base.EditError` so the repair loop can react.
"""
from __future__ import annotations

from typing import Any, ClassVar

from envgen.edit.base import EditError, EditOp, clone_scene, register_op
from envgen.schema import EntityType, SceneGraph

# Which props each entity type allows, and the type they expect.
_PROP_TYPES: dict[EntityType, set[str]] = {
    EntityType.DOOR: {"locked"},
    EntityType.KEY: {"opens"},
}


@register_op
class SetProp(EditOp):
    """Set ``prop`` to ``value`` on the object identified by ``id``."""

    op: ClassVar[str] = "SetProp"

    def __init__(self, id: str, prop: str, value: Any) -> None:
        self.id = id
        self.prop = prop
        self.value = value

    # -- application -------------------------------------------------------
    def apply(self, scene: SceneGraph) -> SceneGraph:
        """Return a new scene with ``prop`` set on ``id``. Pure; never mutates input."""
        new_scene = clone_scene(scene)
        target = new_scene.get(self.id)
        if target is None:
            raise EditError(f"SetProp: unknown object id {self.id!r}")

        allowed = _PROP_TYPES.get(target.type, set())
        if self.prop not in allowed:
            allowed_str = ", ".join(sorted(allowed)) or "(none)"
            raise EditError(
                f"SetProp: prop {self.prop!r} not valid for {target.type.value} "
                f"{self.id!r}; valid props: {allowed_str}"
            )

        if self.prop == "locked":
            target.locked = bool(self.value)
        elif self.prop == "opens":
            self._set_opens(new_scene, target)
        return new_scene

    def _set_opens(self, scene: SceneGraph, target: Any) -> None:
        """Validate and apply an ``opens`` value (a Door id, or ``None`` to clear)."""
        if self.value is None:
            target.opens = None
            return
        door_id = str(self.value)
        door = scene.get(door_id)
        if door is None:
            raise EditError(
                f"SetProp: key {self.id!r} opens unknown id {door_id!r}"
            )
        if door.type is not EntityType.DOOR:
            raise EditError(
                f"SetProp: key {self.id!r} opens {door_id!r}, which is a "
                f"{door.type.value}, not a Door"
            )
        target.opens = door_id

    # -- inverse -----------------------------------------------------------
    def inverse(self, scene: SceneGraph) -> "SetProp":
        """Restore the prior value of ``prop`` read from the pre-state ``scene``."""
        target = scene.get(self.id)
        if target is None:
            raise EditError(f"SetProp: cannot invert, unknown object id {self.id!r}")
        prior = getattr(target, self.prop)
        return SetProp(id=self.id, prop=self.prop, value=prior)

    # -- (de)serialization -------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, "id": self.id, "prop": self.prop, "value": self.value}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SetProp":
        for key in ("id", "prop", "value"):
            if key not in data:
                raise EditError(f"SetProp dict missing required field {key!r}: {data!r}")
        return cls(id=str(data["id"]), prop=str(data["prop"]), value=data["value"])

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SetProp):
            return NotImplemented
        return (self.id, self.prop, self.value) == (other.id, other.prop, other.value)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"SetProp(id={self.id!r}, prop={self.prop!r}, value={self.value!r})"
