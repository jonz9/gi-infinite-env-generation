"""HarnessSession — the live, changing world (ticket S2-T02, the Stage-2 spine).

A :class:`HarnessSession` holds a *live* :class:`~envgen.schema.SceneGraph` plus an
ordered op-log, and grows/mutates it one ``step`` at a time while holding the
solvability invariant. Every step is **atomic and all-or-nothing**: the ops are
applied to a *clone* (via :func:`~envgen.edit.apply_ops`), the result is
re-verified with the frozen :func:`~envgen.validate.validate` +
:func:`~envgen.solve.solve`, and the batch is committed only if the resulting
world is both valid and provably solvable. Otherwise the prior scene is kept
untouched and the batch is recorded as rejected.

This module implements :class:`~envgen.session.base.HarnessSessionProtocol`. It
inlines the minimal op-log / transcript / scene-hash logic it needs rather than
depending on the sibling Stage-2 modules (``oplog.py``, ``transcript_build.py``,
``guard.py``), which are written in parallel against the same frozen contract.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence

from envgen.edit import EditError, EditOp, apply_ops, op_from_dict
from envgen.objective_solve import solve_objective
from envgen.render import render_scene
from envgen.schema import SceneGraph
from envgen.session.base import OpLogEntry, Transcript
from envgen.validate import validate


def _scene_hash(scene: SceneGraph) -> str:
    """Stable hash of a scene's canonical JSON — for replay verification."""
    canonical = json.dumps(scene.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _coerce(op: Any) -> EditOp:
    """Accept an :class:`EditOp` or its ``to_dict()`` form; return an EditOp."""
    return op_from_dict(op) if isinstance(op, dict) else op


class HarnessSession:
    """A persistent, edit-driven world that stays solvable across steps.

    Attributes
    ----------
    scene: the current, live :class:`SceneGraph` (replaced atomically on commit).
    solved: ``True`` iff :data:`scene` is provably solvable right now.
    seed: determinism seed carried for replay/persistence (Stage-2 siblings).
    """

    def __init__(self, scene: SceneGraph, seed: int = 0) -> None:
        self.scene = scene
        self.seed = seed
        self._log: list[OpLogEntry] = []
        # the invariant is the typed objective (legacy 'reach exit' included), so an
        # edit that keeps the exit reachable but breaks the objective is still rejected
        self.solved = bool(validate(scene).ok and solve_objective(scene).solved)

    def log(self) -> list[OpLogEntry]:
        """The ordered op-log (accepted + rejected); with the seed, reproduces state."""
        return list(self._log)

    def step(self, ops: Sequence[EditOp]) -> Transcript:
        """Apply ``ops`` atomically; commit iff the result is valid AND solvable."""
        norm = [_coerce(op) for op in ops]
        before = render_scene(self.scene)
        try:
            op_dicts = [op.to_dict() for op in norm]
        except Exception as exc:  # malformed op object
            return self._reject([], f"could not serialize ops: {exc}", before)

        try:
            candidate = apply_ops(self.scene, norm)
        except EditError as exc:
            return self._reject(op_dicts, str(exc), before)

        report = validate(candidate)
        result = solve_objective(candidate) if report.ok else None
        ok = report.ok and result is not None and result.solved
        if not ok:
            reason = "; ".join(report.errors) or (
                result.reason if result is not None else "unsolvable"
            )
            return self._reject(op_dicts, reason, before)
        return self._commit(candidate, op_dicts, before)

    # -- internals ---------------------------------------------------------
    def _commit(
        self, candidate: SceneGraph, op_dicts: list[dict[str, Any]], before: str
    ) -> Transcript:
        """Replace the live scene, log the accepted ops, build the Transcript."""
        self.scene = candidate
        self.solved = True
        h = _scene_hash(candidate)
        for d in op_dicts:
            self._log.append(OpLogEntry(op=d, accepted=True, reason="ok", scene_hash=h))
        return Transcript(
            applied=list(op_dicts),
            rejected=[],
            valid=True,
            solved=True,
            errors=[],
            render_before=before,
            render_after=render_scene(candidate),
            note=f"applied {len(op_dicts)} op(s); SOLVED",
        )

    def _reject(
        self, op_dicts: list[dict[str, Any]], reason: str, before: str
    ) -> Transcript:
        """Keep the prior scene; log the whole batch as rejected; build the Transcript."""
        for d in op_dicts:
            self._log.append(OpLogEntry(op=d, accepted=False, reason=reason, scene_hash=""))
        return Transcript(
            applied=[],
            rejected=[(d, reason) for d in op_dicts],
            valid=True,  # the *kept* scene still satisfies the invariant
            solved=self.solved,
            errors=[reason],
            render_before=before,
            render_after=before,
            note=f"rejected {len(op_dicts)} op(s): {reason}",
        )
