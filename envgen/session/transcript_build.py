"""Transcript builder — pure formatting of one ``session.step(...)`` outcome.

Given the before/after scenes, the accepted/rejected ops, and the verification
results (a :class:`~envgen.validate.ValidationReport` + a
:class:`~envgen.solve.SolveResult`), assemble the frozen
:class:`~envgen.session.base.Transcript` record: ASCII renders framing the diff,
the ``valid``/``solved``/``errors`` fields, and a one-line human ``note``.

This module is intentionally side-effect-free: it builds a value, never mutates a
scene, holds no state, and re-runs no verification. The renders come straight from
:func:`envgen.render.render_scene` (no dependency on ``edit.diff``).
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from envgen.render import render_scene
from envgen.schema import SceneGraph
from envgen.session.base import Transcript

# Imported only for typing/clarity; not required at call time.
from envgen.solve import SolveResult
from envgen.validate import ValidationReport


def build_transcript(
    before: SceneGraph,
    after: SceneGraph,
    applied: Sequence[dict[str, Any]],
    rejected: Sequence[tuple[dict[str, Any], str]],
    report: Optional[ValidationReport],
    solve_result: Optional[SolveResult],
) -> Transcript:
    """Compose a :class:`Transcript` from a step's inputs and verification results.

    Parameters
    ----------
    before / after: scenes framing the edit (rendered to ASCII for the diff).
    applied: op dicts accepted and applied this step.
    rejected: ``(op_dict, reason)`` pairs refused to keep the invariant.
    report: validation outcome; ``valid`` and ``errors`` are read from it.
    solve_result: solvability proof; ``solved`` and the action count are read here.

    Pure formatting: no mutation, no state, no re-verification.
    """
    applied_list = [dict(op) for op in applied]
    rejected_list = [(dict(op), reason) for op, reason in rejected]

    valid = bool(report.ok) if report is not None else True
    errors = list(report.errors) if report is not None else []
    solved = bool(solve_result.solved) if solve_result is not None else True

    return Transcript(
        applied=applied_list,
        rejected=rejected_list,
        valid=valid,
        solved=solved,
        errors=errors,
        render_before=render_scene(before),
        render_after=render_scene(after),
        note=_note(applied_list, rejected_list, valid, solve_result),
    )


def _note(
    applied: list[dict[str, Any]],
    rejected: list[tuple[dict[str, Any], str]],
    valid: bool,
    solve_result: Optional[SolveResult],
) -> str:
    """Build the one-line human summary, e.g. ``"applied 2 ops; SOLVED in 14"``."""
    parts = [f"applied {len(applied)} op{_s(len(applied))}"]
    if rejected:
        parts.append(f"{len(rejected)} rejected")
    head = ", ".join(parts)
    return f"{head}; {_verdict(valid, solve_result)}"


def _verdict(valid: bool, solve_result: Optional[SolveResult]) -> str:
    """Summarize the post-step status for the note."""
    if not valid:
        return "INVALID"
    if solve_result is None:
        return "unsolved"
    if solve_result.solved:
        return f"SOLVED in {len(solve_result.actions)}"
    return "FAILED"


def _s(n: int) -> str:
    """Pluralization helper: ``""`` for 1, ``"s"`` otherwise."""
    return "" if n == 1 else "s"
