"""Session stats — a read-only snapshot of a live :class:`HarnessSession`.

``stats(session)`` summarizes the current world and its edit history into a plain
JSON-friendly dict, **without ever mutating the session**. It reads the frozen
:class:`~envgen.session.base.HarnessSessionProtocol` surface only: ``.scene``,
``.solved``, and ``.log()``.

Reported keys
-------------
``edits``: ``{"applied", "rejected", "total"}`` tallied from the op-log.
``solution_length``: number of actions the solver needs on the *current* scene
    (``None`` if unsolvable). Computed fresh via :func:`~envgen.solve.solve` since
    the protocol exposes no cached value.
``solved``: the session's current solvability flag.
``grid``: ``{"w", "h", "area"}`` of the current scene's tile layer.
``objects``: ``{"total", "by_type": {<EntityType.value>: count, ...}}``.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from envgen.schema import SceneGraph
from envgen.session.base import HarnessSessionProtocol
from envgen.solve import solve


def stats(session: HarnessSessionProtocol) -> dict[str, Any]:
    """Return a read-only stats dict for ``session`` (never mutates it)."""
    return {
        "edits": _edit_counts(session),
        "solution_length": _solution_length(session.scene),
        "solved": bool(session.solved),
        "grid": _grid_size(session.scene),
        "objects": _object_counts(session.scene),
    }


def _edit_counts(session: HarnessSessionProtocol) -> dict[str, int]:
    """Tally accepted vs rejected entries from the op-log."""
    entries = session.log()
    applied = sum(1 for e in entries if e.accepted)
    rejected = len(entries) - applied
    return {"applied": applied, "rejected": rejected, "total": len(entries)}


def _solution_length(scene: SceneGraph) -> int | None:
    """Action count the solver needs on ``scene`` (``None`` if unsolvable)."""
    result = solve(scene)
    return len(result.actions) if result.solved else None


def _grid_size(scene: SceneGraph) -> dict[str, int]:
    """Width, height, and area of the scene's tile layer."""
    w, h = scene.grid.w, scene.grid.h
    return {"w": w, "h": h, "area": w * h}


def _object_counts(scene: SceneGraph) -> dict[str, Any]:
    """Total object count plus a per-:class:`EntityType` breakdown."""
    by_type = Counter(o.type.value for o in scene.objects)
    return {"total": len(scene.objects), "by_type": dict(by_type)}
