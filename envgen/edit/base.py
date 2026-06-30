"""Edit algebra — frozen contracts for the typed edit operations.

⚠️ FROZEN FILE. Do not edit as part of a ticket. This module defines the *stable
contract* every edit op implements and the registry that discovers them. Tickets
add op modules under ``envgen/edit/ops/`` that self-register; they never touch this
file. See ``tickets/README.md``.

An **edit op** is a pure, serializable transform on a :class:`~envgen.schema.SceneGraph`:

    new_scene = op.apply(scene)        # returns a NEW scene; never mutates ``scene``

Ops are the *verbs* of the IR (the scene graph was the noun). Natural language
compiles to a list of these; the harness applies them and re-verifies solvability.
Because each op is plain data (``to_dict``/``from_dict``) the handoff stays JSON —
no code generation, consistent with the rest of the project.
"""
from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from envgen.schema import SceneGraph


class EditError(ValueError):
    """Raised when an op cannot apply (bad target id, out-of-bounds, overlap, ...).

    The message is intentionally specific so the NL→ops repair loop (Stage 3) can
    feed it straight back to the compiler — mirroring :class:`~envgen.schema.SchemaError`.
    """


def clone_scene(scene: SceneGraph) -> SceneGraph:
    """Deep-copy a scene so an op can mutate the copy and leave the input untouched.

    Every op MUST build its result from ``clone_scene(scene)`` (or an equivalent
    fresh construction) so application is referentially transparent — that is what
    makes the op-log replayable and rollback exact.
    """
    return copy.deepcopy(scene)


class EditOp(ABC):
    """Base class / contract for one typed edit operation.

    Implementations live one-per-file under ``envgen/edit/ops/`` and decorate
    themselves with :func:`register_op`. They must:

    * set the ``op`` class var to a unique registry key (e.g. ``"AddObject"``);
    * implement :meth:`apply` as a pure function (no mutation of ``scene``);
    * implement :meth:`to_dict`/:meth:`from_dict` round-tripping through JSON, where
      ``to_dict()`` includes ``{"op": <type>}``;
    * raise :class:`EditError` with a specific message on any precondition failure.

    :meth:`inverse` is optional (used by undo/rollback); the default signals that
    the op is not invertible, and the session falls back to snapshot rollback.
    """

    op: ClassVar[str]

    @abstractmethod
    def apply(self, scene: SceneGraph) -> SceneGraph:
        """Return a new scene with this op applied. Must not mutate ``scene``."""

    def inverse(self, scene: SceneGraph) -> "EditOp":
        """Return the op that undoes this one *given the pre-state* ``scene``.

        Optional. Override when a cheap structural inverse exists; otherwise the
        session uses snapshot rollback. The default raises to say "not invertible".
        """
        raise NotImplementedError(f"{type(self).__name__} has no structural inverse")

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-able dict including ``{"op": self.op}``."""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditOp":
        """Parse one op dict (the ``op`` key already routed here by the registry)."""


# --- registry (auto-populated by ops/ modules via the decorator) --------------
_REGISTRY: dict[str, type[EditOp]] = {}


def register_op(cls: type[EditOp]) -> type[EditOp]:
    """Class decorator: register an :class:`EditOp` subclass under its ``op`` key.

    Used as ``@register_op`` above each op class. Raises if the ``op`` key collides,
    so two tickets cannot silently claim the same verb.
    """
    key = getattr(cls, "op", None)
    if not key:
        raise ValueError(f"{cls.__name__} must set a non-empty `op` class var")
    if key in _REGISTRY and _REGISTRY[key] is not cls:
        raise ValueError(f"edit op {key!r} already registered by {_REGISTRY[key].__name__}")
    _REGISTRY[key] = cls
    return cls


def registered_ops() -> dict[str, type[EditOp]]:
    """A copy of the op registry, keyed by op type. Triggers op discovery."""
    from envgen.edit import ops as _ops  # noqa: F401 - import for side-effect (discovery)

    return dict(_REGISTRY)


def op_from_dict(data: dict[str, Any]) -> EditOp:
    """Construct the right :class:`EditOp` from a dict by its ``"op"`` key."""
    if "op" not in data:
        raise EditError(f"edit op dict missing 'op' key: {data!r}")
    registry = registered_ops()
    key = data["op"]
    if key not in registry:
        valid = ", ".join(sorted(registry)) or "(none registered)"
        raise EditError(f"unknown edit op {key!r}; registered: {valid}")
    return registry[key].from_dict(data)
