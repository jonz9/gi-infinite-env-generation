"""Op dry-run / preview — try an edit op without committing it.

This is the "what would happen if I applied this op?" probe the session uses
before accepting an op into its log. It applies the op to a *clone* of the scene
and runs the full :func:`envgen.validate.validate` pass, then throws the result
away — the caller's ``scene`` is never mutated and nothing is committed.

It re-uses existing machinery only: :meth:`EditOp.apply` (which itself builds
from ``clone_scene``) for the transform and :func:`envgen.validate.validate` for
the verdict. No rule is re-implemented here.

Return contract — :func:`preview` ``-> (ok, report_or_msg)``:

* ``(True,  ValidationReport)`` — the op applied and the result validates clean.
* ``(False, ValidationReport)`` — the op applied but the result is invalid
  (``report.errors`` is non-empty); the session can surface those errors.
* ``(False, str)``             — the op itself raised :class:`EditError`; the
  message is returned verbatim for the repair loop.
"""
from __future__ import annotations

from envgen.edit.base import EditError, EditOp, clone_scene
from envgen.schema import SceneGraph
from envgen.validate import ValidationReport, validate


def preview(scene: SceneGraph, op: EditOp) -> tuple[bool, ValidationReport | str]:
    """Dry-run ``op`` against ``scene`` and report the outcome without committing.

    ``scene`` is never mutated: the op is applied to a defensive
    :func:`~envgen.edit.base.clone_scene` copy and the validated result is
    discarded. See the module docstring for the full return contract.
    """
    sandbox = clone_scene(scene)
    try:
        candidate = op.apply(sandbox)
    except EditError as exc:
        return False, str(exc)
    report = validate(candidate)
    return report.ok, report
