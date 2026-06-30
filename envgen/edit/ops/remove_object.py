"""RemoveObject — delete the object with a given id from the scene graph.

One verb of the edit algebra (see ``tickets/stage-1-edit-algebra.md``, S1-T02).
Pure transform: builds its result from :func:`~envgen.edit.base.clone_scene` and
never mutates the input scene.

Dangling ``Key.opens`` policy
-----------------------------
Removing a Door that one or more Keys still reference via ``opens`` would leave
those references dangling. This op **leaves such references untouched** rather
than rewriting or deleting other objects. Rationale:

* RemoveObject stays a *single-object* operation — predictable and exactly
  invertible (its :meth:`inverse` reconstructs just the one removed object; it
  does not have to remember mutations it made to sibling Keys).
* The dangling reference is not silently swallowed: ``schema.check_well_formed``
  already reports ``key <id> opens unknown door <id>``, so the harness's
  validation step surfaces it for the repair loop to fix with a follow-up op
  (e.g. ``SetProp`` to clear ``opens`` or ``RemoveObject`` on the Key).

In short: we *leave the ref* and rely on the existing structural validator to
flag it, keeping this op minimal and reversible.
"""
from __future__ import annotations

from typing import Any

from envgen.edit.base import EditError, EditOp, clone_scene, op_from_dict, register_op
from envgen.schema import SceneGraph


@register_op
class RemoveObject(EditOp):
    """Remove the object identified by ``id`` from the scene's object layer."""

    op = "RemoveObject"

    def __init__(self, id: str) -> None:
        self.id = id

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"RemoveObject(id={self.id!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RemoveObject) and other.id == self.id

    def apply(self, scene: SceneGraph) -> SceneGraph:
        """Return a new scene with object ``id`` removed (input untouched)."""
        result = clone_scene(scene)
        target = result.get(self.id)
        if target is None:
            raise EditError(
                f"RemoveObject: no object with id {self.id!r} in scene "
                f"(have: {', '.join(o.id for o in result.objects) or '(none)'})"
            )
        result.objects = [o for o in result.objects if o.id != self.id]
        return result

    def inverse(self, scene: SceneGraph) -> EditOp:
        """Return an ``AddObject`` op that re-adds the object removed from ``scene``.

        Built lazily from the *pre-state* via :func:`op_from_dict` so this module
        carries no import-time dependency on the AddObject module.
        """
        target = scene.get(self.id)
        if target is None:
            raise EditError(
                f"RemoveObject.inverse: object {self.id!r} is not present in the "
                f"given pre-state scene; cannot reconstruct it"
            )
        return op_from_dict({"op": "AddObject", **target.to_dict()})

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, "id": self.id}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RemoveObject":
        if "id" not in data:
            raise EditError(f"RemoveObject op dict missing required 'id': {data!r}")
        return cls(id=str(data["id"]))
