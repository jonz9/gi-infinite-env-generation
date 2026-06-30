"""Undo / redo for a live :class:`HarnessSession` (ticket S2-T14).

A session grows and mutates one :func:`~envgen.session.core.HarnessSession.step`
at a time, holding the solvability invariant. This module layers a classic
undo/redo cursor on top of that op-log.

Strategy — **snapshot-based, for robustness.** Each accepted commit produces a
new scene state; we keep a stack of deep-copied :class:`~envgen.schema.SceneGraph`
snapshots and move a cursor over them. Restoring a snapshot is exact regardless of
whether the contributing ops expose a structural :meth:`~envgen.edit.base.EditOp.inverse`
(many do not, e.g. ``RemoveObject``), which is why we snapshot rather than replay
inverses. Because every snapshot was a *committed* (valid + solvable) state, undo
and redo always land on a world that still satisfies the invariant.

The hash of a restored scene is computed exactly as
:mod:`envgen.session.core` computes it, so ``undo`` then ``redo`` returns the scene
to a state whose hash matches the pre-undo state (the acceptance criterion).

Usage::

    hist = History(session)        # snapshots the starting state
    hist.step([op_a])              # like session.step, but records a snapshot
    hist.step([op_b])
    hist.undo()                    # scene back to the post-op_a state
    hist.redo()                    # forward again to the post-op_b state

The module-level :func:`undo` / :func:`redo` operate on a per-session
:class:`History` (created lazily and cached), so callers can also drive undo/redo
without holding the wrapper directly.
"""
from __future__ import annotations

import hashlib
import json
from typing import Sequence

from envgen.edit import EditOp, clone_scene
from envgen.schema import SceneGraph
from envgen.session.base import HarnessSessionProtocol, Transcript
from envgen.solve import solve
from envgen.validate import validate


def scene_hash(scene: SceneGraph) -> str:
    """Stable hash of a scene's canonical JSON.

    Matches the hashing in :mod:`envgen.session.core` so snapshots and op-log
    ``scene_hash`` values are directly comparable.
    """
    canonical = json.dumps(scene.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class History:
    """Undo/redo cursor over the committed states of a :class:`HarnessSession`.

    Wraps any object satisfying :class:`HarnessSessionProtocol`. The starting
    scene is snapshotted on construction; subsequent committed states are captured
    by :meth:`step` (and best-effort by :meth:`sync` for direct ``session.step``
    calls). :meth:`undo` / :meth:`redo` move a cursor and restore the live scene.
    """

    def __init__(self, session: HarnessSessionProtocol) -> None:
        self.session = session
        # Snapshot stack of committed scenes; index 0 is the starting state.
        self._states: list[SceneGraph] = [clone_scene(session.scene)]
        self._cursor = 0
        self._last_seen_hash = scene_hash(session.scene)

    # -- step (records snapshots) -----------------------------------------
    def step(self, ops: Sequence[EditOp]) -> Transcript:
        """Delegate to ``session.step``; snapshot the new state if it committed."""
        self.sync()  # fold in any direct steps before branching
        transcript = self.session.step(ops)
        if transcript.applied:
            self._record_current()
        return transcript

    def sync(self) -> None:
        """Capture a direct ``session.step`` commit not made through this History.

        Best-effort: if the live scene differs from the last state we recorded,
        push it as a new committed state (collapsing any intervening commits).
        """
        current = scene_hash(self.session.scene)
        if current != self._last_seen_hash:
            self._record_current()

    def _record_current(self) -> None:
        """Truncate any redo branch and append the live scene as a new state."""
        del self._states[self._cursor + 1:]
        self._states.append(clone_scene(self.session.scene))
        self._cursor = len(self._states) - 1
        self._last_seen_hash = scene_hash(self.session.scene)

    # -- undo / redo ------------------------------------------------------
    def can_undo(self) -> bool:
        return self._cursor > 0

    def can_redo(self) -> bool:
        return self._cursor < len(self._states) - 1

    def undo(self) -> bool:
        """Restore the previous committed state. Returns ``False`` past the start."""
        self.sync()
        if not self.can_undo():
            return False
        self._cursor -= 1
        self._restore(self._states[self._cursor])
        return True

    def redo(self) -> bool:
        """Restore the next committed state. Returns ``False`` past the end."""
        if not self.can_redo():
            return False
        self._cursor += 1
        self._restore(self._states[self._cursor])
        return True

    def current_hash(self) -> str:
        """Hash of the state the cursor currently points at."""
        return scene_hash(self._states[self._cursor])

    # -- internals --------------------------------------------------------
    def _restore(self, scene: SceneGraph) -> None:
        """Make ``scene`` the session's live scene and refresh ``solved``."""
        restored = clone_scene(scene)
        self.session.scene = restored
        # Every snapshot was a committed (valid+solvable) state; recompute to keep
        # the session's invariant flag exact rather than assuming it.
        self.session.solved = bool(validate(restored).ok and solve(restored).solved)
        self._last_seen_hash = scene_hash(restored)


# --- module-level convenience over a cached per-session History ---------------
_TRACKERS: dict[int, History] = {}


def history_for(session: HarnessSessionProtocol) -> History:
    """Return the :class:`History` tracking ``session``, creating it on first use.

    Cached by object identity. For undo to reach states predating the first call,
    obtain the History (or call :func:`undo`/:func:`redo`) before editing.
    """
    existing = _TRACKERS.get(id(session))
    if existing is not None and existing.session is session:
        return existing
    tracker = History(session)
    _TRACKERS[id(session)] = tracker
    return tracker


def undo(session: HarnessSessionProtocol) -> bool:
    """Undo the most recent committed step on ``session``. ``False`` past the start."""
    return history_for(session).undo()


def redo(session: HarnessSessionProtocol) -> bool:
    """Redo the most recently undone step on ``session``. ``False`` past the end."""
    return history_for(session).redo()
