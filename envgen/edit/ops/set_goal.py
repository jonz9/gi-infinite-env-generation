"""SetGoal — replace the scene's natural-language goal string.

Self-registering :class:`~envgen.edit.base.EditOp` under the ``"SetGoal"`` key.
Replaces ``scene.goal`` (a short free-text string like ``"reach exit"``) with a
new value, rejecting (with a specific :class:`~envgen.edit.base.EditError`) a
non-string or empty/whitespace-only goal. Application is pure: the result is
built from ``clone_scene(scene)`` so the input is never mutated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from envgen.edit.base import EditError, EditOp, clone_scene, register_op
from envgen.schema import SceneGraph


@register_op
@dataclass
class SetGoal(EditOp):
    """Set the scene goal to ``goal`` (a non-empty short string)."""

    op = "SetGoal"

    goal: str

    @staticmethod
    def _validate(goal: Any) -> str:
        if not isinstance(goal, str):
            raise EditError(
                f"SetGoal: goal must be a string, got {type(goal).__name__} ({goal!r})"
            )
        if not goal.strip():
            raise EditError("SetGoal: goal must be a non-empty string")
        return goal

    def apply(self, scene: SceneGraph) -> SceneGraph:
        new_goal = self._validate(self.goal)
        result = clone_scene(scene)
        result.goal = new_goal
        return result

    def inverse(self, scene: SceneGraph) -> "SetGoal":
        return SetGoal(goal=scene.goal)

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, "goal": self.goal}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SetGoal":
        if "goal" not in data:
            raise EditError(f"SetGoal: missing required field 'goal': {data!r}")
        return cls(goal=cls._validate(data["goal"]))
