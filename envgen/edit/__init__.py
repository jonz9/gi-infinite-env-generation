"""Edit algebra — the typed *verbs* of the scene-graph IR.

Public surface (frozen): the :class:`~envgen.edit.base.EditOp` contract, the
registry (:func:`register_op`, :func:`registered_ops`, :func:`op_from_dict`), and
the pure :func:`apply_op` / :func:`apply_ops` helpers. Concrete ops live one-per-file
under :mod:`envgen.edit.ops` and are discovered automatically.

Importing this package triggers op discovery, so ``registered_ops()`` reflects
every op module present in the tree.
"""
from envgen.edit.apply import apply_op, apply_ops, ops_from_dicts
from envgen.edit.base import (
    EditError,
    EditOp,
    clone_scene,
    op_from_dict,
    register_op,
    registered_ops,
)
from envgen.edit import ops as _ops  # noqa: F401 - trigger auto-discovery on import

__all__ = [
    "EditError",
    "EditOp",
    "apply_op",
    "apply_ops",
    "clone_scene",
    "op_from_dict",
    "ops_from_dicts",
    "register_op",
    "registered_ops",
]
