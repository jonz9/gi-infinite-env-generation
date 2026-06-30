"""Replay / determinism checker (ticket S2-T08).

The determinism invariant made executable: ``seed + initial scene + accepted
op-log`` must reproduce the live scene *hash-for-hash*. Persistence (S2-T07)
relies on this — it stores only those three things and reconstructs by replay.

Two surfaces:

* :func:`replay` — a pure, standalone fold of the *accepted* ops of an op-log
  over an initial scene. No session required; trivially testable.
* :func:`check_replay` — replays a live :class:`~envgen.session.core.HarnessSession`'s
  accepted log and proves the result hashes identically to ``session.scene``,
  reporting the first op index whose post-state diverges.

Obtaining the initial scene
---------------------------
``HarnessSession`` (``core.py``) keeps only the *live* scene, the ``seed`` and the
op-log — it does **not** expose the pre-edit scene. So :func:`check_replay` cannot
reconstruct the world from the session alone; the caller must supply the initial
scene (snapshotted before any edits), either via the ``initial`` argument or via an
``initial_scene`` attribute on the session if a future implementation exposes one.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional, Sequence

from envgen.edit import EditError, apply_ops, op_from_dict
from envgen.schema import SceneGraph
from envgen.session.base import OpLogEntry, ReplayCheck


def scene_hash(scene: SceneGraph) -> str:
    """Stable hash of a scene's canonical JSON.

    Matches ``core.py``'s ``_scene_hash`` byte-for-byte so a replayed scene hashes
    identically to the value the session recorded on each :class:`OpLogEntry`.
    """
    canonical = json.dumps(scene.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _accepted(oplog: Sequence[OpLogEntry]) -> list[OpLogEntry]:
    """The accepted entries of an op-log, in order (rejected ops never applied)."""
    return [e for e in oplog if e.accepted]


def replay(seed: int, initial: SceneGraph, oplog: Sequence[OpLogEntry]) -> SceneGraph:
    """Fold the *accepted* ops of ``oplog`` over ``initial``, returning the result.

    Each entry's ``op`` dict is parsed via
    :func:`~envgen.edit.op_from_dict` and applied with
    :func:`~envgen.edit.apply_ops` (which never mutates its input). ``seed`` is part
    of the determinism contract and carried for symmetry with persistence; the ops
    themselves are fully deterministic, so it does not alter the fold.
    """
    ops = [op_from_dict(entry.op) for entry in _accepted(oplog)]
    # apply_ops builds each step from clone_scene(...), so ``initial`` is untouched.
    return apply_ops(initial, ops)


def check_replay(
    session: object, initial: Optional[SceneGraph] = None
) -> ReplayCheck:
    """Replay ``session``'s accepted op-log and prove it reproduces ``session.scene``.

    Returns a :class:`ReplayCheck` with ``ok=True`` when the replayed scene hashes
    identically to the live scene. On a mismatch, ``diverged_at`` is the index (into
    the accepted-ops sequence) of the first op whose post-state fails to match what
    the session recorded.

    The initial (pre-edit) scene is taken from ``initial`` if given, else from a
    ``session.initial_scene`` attribute if present; otherwise a clear error is
    raised, since the session core does not retain it (see module docstring).
    """
    if initial is None:
        initial = getattr(session, "initial_scene", None)
    if initial is None:
        raise ValueError(
            "check_replay needs the initial (pre-edit) scene: HarnessSession does "
            "not retain it. Pass initial=<scene snapshot taken before any edits>, "
            "or expose session.initial_scene."
        )

    seed = getattr(session, "seed", 0)
    accepted = _accepted(session.log())
    live_hash = scene_hash(session.scene)

    diverged_at = _first_divergence(seed, initial, accepted)
    if diverged_at is not None:
        return ReplayCheck(
            ok=False,
            diverged_at=diverged_at,
            detail=f"op #{diverged_at} post-state diverges from the recorded op-log",
        )

    # No per-op divergence: confirm the full replay matches the live scene.
    replayed_hash = scene_hash(replay(seed, initial, accepted))
    if replayed_hash != live_hash:
        last = max(len(accepted) - 1, 0)
        return ReplayCheck(
            ok=False,
            diverged_at=last,
            detail="replayed scene hash does not match the live session scene",
        )
    return ReplayCheck(ok=True, detail=f"replayed {len(accepted)} accepted op(s)")


def _first_divergence(
    seed: int, initial: SceneGraph, accepted: list[OpLogEntry]
) -> Optional[int]:
    """Index of the first accepted op whose post-state diverges from the log.

    Replays op-by-op. The session commits a *batch* atomically, recording the same
    ``scene_hash`` (the batch-final hash) on every entry of that batch. So an entry's
    recorded hash is only authoritative at a **batch boundary** — the last entry of a
    run sharing one hash. We check the cumulative replay hash against the recorded
    hash exactly at those boundaries; an op that raises :class:`EditError` (e.g. a
    tampered target) diverges immediately.
    """
    scene = initial
    for i, entry in enumerate(accepted):
        try:
            scene = apply_ops(scene, [op_from_dict(entry.op)])
        except EditError:
            return i
        is_boundary = i + 1 == len(accepted) or accepted[i + 1].scene_hash != entry.scene_hash
        if is_boundary and entry.scene_hash and scene_hash(scene) != entry.scene_hash:
            return i
    return None
