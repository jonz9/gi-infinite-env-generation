"""Session branching / fork (ticket S2-T13) — counterfactual generation.

:func:`fork` makes a child :class:`~envgen.session.core.HarnessSession` that shares
the parent's *history up to the fork point* but diverges afterward. Edits applied to
the fork never touch the parent, and vice-versa, so a single solvable state can spawn
two independent variants ("two harder versions from one room"). The child is built by
deep-copying the live scene plus the op-log and constructing a fresh session — no
re-derivation of state, and no shared mutable references between parent and child.
"""
from __future__ import annotations

import copy

from envgen.session.core import HarnessSession


def fork(session: HarnessSession) -> HarnessSession:
    """Return an independent deep copy of ``session`` for counterfactual edits.

    The fork starts from the same live scene, carries over the parent's op-log
    (its shared history up to the fork point), and preserves ``seed`` / ``solved``.
    Because the scene and log are deep-copied, subsequent edits on either session
    leave the other unchanged.
    """
    child = HarnessSession(copy.deepcopy(session.scene), seed=getattr(session, "seed", 0))
    # Carry over the shared history; deep-copy so the two logs diverge independently
    # (each ``OpLogEntry`` is frozen, but its ``op`` dict is mutable).
    child._log = copy.deepcopy(session.log())
    child.solved = session.solved
    return child
