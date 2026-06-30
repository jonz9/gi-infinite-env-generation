"""Invariant guard / rollback policy (ticket S2-T06).

A pure helper encapsulating the accept-or-rollback decision the session core makes
when a batch of edits arrives. It applies ops to a *clone* and re-checks the two
harness invariants — structural/placement validity and provable solvability — via
injected ``validate_fn`` / ``solve_fn`` (the frozen :func:`envgen.validate.validate`
and :func:`envgen.solve.solve`). It never mutates the input scene, and it never
re-implements verification; it only orchestrates rollback.

Two policies
------------
* ``"atomic"`` — all-or-nothing. Apply the whole batch to a clone; if any op raises
  :class:`~envgen.edit.base.EditError` or the resulting scene fails validation /
  solvability, reject the *entire* batch and return the original scene unchanged.
* ``"greedy"`` — apply ops one at a time, keeping each only while the running scene
  still validates *and* solves; an op that raises or that breaks an invariant is
  recorded as rejected and skipped, and the next op is tried against the last good
  scene (the longest valid run survives).

Recommended for the core
-------------------------
The session core (``S2-T02``) should use **atomic**: its contract is "reject the
whole batch and keep the prior scene" so the op-log stays a clean sequence of
self-consistent commits and replay is exact. Greedy is offered for interactive /
repair tooling that prefers to salvage the good edits in a partially-bad batch.
"""
from __future__ import annotations

from typing import Any, Callable, Protocol, Sequence

from envgen.edit import EditError, EditOp, apply_op
from envgen.schema import SceneGraph


class _Report(Protocol):
    ok: bool
    errors: list[str]


class _SolveResult(Protocol):
    solved: bool
    reason: str


#: ``(op_dict, reason)`` for one refused op (or every op of a rejected batch).
Rejection = tuple[dict[str, Any], str]


def guard_apply(
    scene: SceneGraph,
    ops: Sequence[EditOp],
    *,
    validate_fn: Callable[[SceneGraph], _Report],
    solve_fn: Callable[[SceneGraph], _SolveResult],
    policy: str = "atomic",
) -> tuple[SceneGraph, list[Rejection]]:
    """Apply ``ops`` to ``scene`` under an invariant-preserving rollback ``policy``.

    Returns ``(accepted_scene, rejected)`` where ``accepted_scene`` is the new scene
    holding only the accepted edits (the original, unmutated, if nothing was kept)
    and ``rejected`` is a list of ``(op_dict, reason)`` explaining every refusal.

    The input ``scene`` is never mutated (ops build from ``clone_scene``); on a full
    atomic rollback the very same object is returned.
    """
    if policy == "atomic":
        return _atomic(scene, ops, validate_fn, solve_fn)
    if policy == "greedy":
        return _greedy(scene, ops, validate_fn, solve_fn)
    raise ValueError(f"unknown guard policy {policy!r}; expected 'atomic' or 'greedy'")


def _violation(
    scene: SceneGraph,
    validate_fn: Callable[[SceneGraph], _Report],
    solve_fn: Callable[[SceneGraph], _SolveResult],
) -> str | None:
    """Return a reason string if ``scene`` breaks an invariant, else ``None``."""
    report = validate_fn(scene)
    if not report.ok:
        return "validation failed: " + "; ".join(report.errors)
    result = solve_fn(scene)
    if not result.solved:
        return f"unsolvable: {result.reason}"
    return None


def _atomic(
    scene: SceneGraph,
    ops: Sequence[EditOp],
    validate_fn: Callable[[SceneGraph], _Report],
    solve_fn: Callable[[SceneGraph], _SolveResult],
) -> tuple[SceneGraph, list[Rejection]]:
    """All-or-nothing: keep the whole batch or none of it."""
    candidate = scene
    for op in ops:
        try:
            candidate = apply_op(candidate, op)
        except EditError as exc:
            return scene, _reject_batch(ops, f"batch rejected: {exc}")
    bad = _violation(candidate, validate_fn, solve_fn)
    if bad is not None:
        return scene, _reject_batch(ops, f"batch rejected: {bad}")
    return candidate, []


def _greedy(
    scene: SceneGraph,
    ops: Sequence[EditOp],
    validate_fn: Callable[[SceneGraph], _Report],
    solve_fn: Callable[[SceneGraph], _SolveResult],
) -> tuple[SceneGraph, list[Rejection]]:
    """Keep each op only while the running scene still validates and solves."""
    current = scene
    rejected: list[Rejection] = []
    for op in ops:
        try:
            candidate = apply_op(current, op)
        except EditError as exc:
            rejected.append((op.to_dict(), f"apply failed: {exc}"))
            continue
        bad = _violation(candidate, validate_fn, solve_fn)
        if bad is not None:
            rejected.append((op.to_dict(), bad))
            continue
        current = candidate
    return current, rejected


def _reject_batch(ops: Sequence[EditOp], reason: str) -> list[Rejection]:
    """Pair every op in a rejected batch with the shared rejection ``reason``."""
    return [(op.to_dict(), reason) for op in ops]
