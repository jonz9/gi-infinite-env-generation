"""Incremental validation wrapper (S2-T03).

:func:`revalidate` is a *correctness-preserving* fast path around the frozen
:func:`envgen.validate.validate`. The session re-validates after every accepted
op batch; most batches touch only a corner of the scene, so re-running the full
three-layer validator (structural + placement + the solvability BFS) is wasteful.

Equivalence is the contract
---------------------------
``revalidate(prev_report, scene, ops)`` MUST return a report equal to
``validate(scene)`` (same ``ok``, same ``errors`` in the same order) on *every*
input. Speed is a bonus; correctness is mandatory. So this module only takes a
shortcut when it can *prove* the result is unchanged, and otherwise delegates to
the full validator.

The single provably-safe shortcut
---------------------------------
``validate`` inspects exactly three things: the grid (topology), the object layer
(positions / types / ``locked`` / ``opens``), and — for solvability — a BFS over
those. It never reads ``scene.goal``. Therefore an op batch whose every op can
only change the goal text (``SetGoal``) cannot change *any* of the three layers:
the post-op report is identical to the pre-op one. In that case we return the
previously computed ``prev_report`` directly and skip all work, including the BFS.

Any batch containing an op that can touch topology or objects is handled by
delegating to ``validate`` — the conservative, always-correct path. (Skipping the
solvability BFS while structural/placement results change would require a cached
solvability outcome that ``prev_report`` does not expose cleanly, so we don't
attempt it: "if in doubt, delegate to full validate".)
"""

from __future__ import annotations

from typing import Any, Iterable

from envgen.schema import SceneGraph
from envgen.validate import ValidationReport, validate

# Op keys whose application provably cannot change any invariant ``validate``
# checks (structural well-formedness, placement/overlap, or solvability). These
# touch only fields the validator ignores — currently just the goal text.
_VALIDATION_IRRELEVANT_OPS: frozenset[str] = frozenset({"SetGoal"})


def _op_key(op: Any) -> str | None:
    """Best-effort op-type key for an :class:`EditOp` instance or an op dict."""
    if isinstance(op, dict):
        return op.get("op")
    return getattr(op, "op", None)


def _affects_validation(op: Any) -> bool:
    """Whether ``op`` could change any invariant ``validate`` inspects.

    Conservative: anything not on the known-irrelevant allowlist (including
    unrecognized ops) is treated as validation-affecting, forcing a full
    re-validation.
    """
    return _op_key(op) not in _VALIDATION_IRRELEVANT_OPS


def revalidate(
    prev_report: ValidationReport,
    scene: SceneGraph,
    ops: Iterable[Any],
) -> ValidationReport:
    """Re-validate ``scene`` after ``ops``, equal to ``validate(scene)`` always.

    ``prev_report`` is the report of the scene *before* ``ops`` were applied
    (i.e. ``validate(prev_scene)``). When every op in the batch is provably
    unable to change a validation invariant, the previous report still holds and
    is returned verbatim — skipping the structural, placement, and solvability
    passes entirely. Otherwise this delegates to the frozen
    :func:`envgen.validate.validate` to guarantee exact equivalence.
    """
    if not any(_affects_validation(op) for op in ops):
        # No op can alter topology, objects, or solvability inputs — and
        # ``validate`` ignores the goal text those ops touch — so the report is
        # unchanged. Copy ``errors`` so callers can't mutate the cached report.
        return ValidationReport(ok=prev_report.ok, errors=list(prev_report.errors))
    return validate(scene)
