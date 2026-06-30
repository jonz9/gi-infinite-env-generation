"""Incremental solve wrapper (S2-T04) — memoized :func:`envgen.solve.solve`.

Re-solving a scene the session has not changed is wasted work: the solver replays
a BFS plan on a fresh env every call. :func:`resolve` caches a :class:`SolveResult`
keyed by a stable hash of the scene's canonical JSON, so an unchanged scene returns
the *same* result object for free, while any structural change recomputes.

The cache is caller-supplied (a plain ``dict``), letting a session own its lifetime;
when ``None`` a fresh dict is created (so a lone call behaves exactly like ``solve``).
Pure stdlib: no sibling-session imports, no global state.
"""

from __future__ import annotations

import hashlib
import json
from typing import Dict, Optional

from envgen.schema import SceneGraph
from envgen.solve import SolveResult, solve


def scene_hash(scene: SceneGraph) -> str:
    """Stable hex digest of ``scene`` via canonical (sorted-key) JSON.

    Two scenes hash equal iff their ``to_dict()`` payloads are equal, independent
    of dict ordering — the property that makes memoization sound.
    """
    canonical = json.dumps(scene.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve(
    scene: SceneGraph, cache: Optional[Dict[str, SolveResult]] = None
) -> SolveResult:
    """Solve ``scene``, reusing a cached :class:`SolveResult` for unchanged scenes.

    On a cache miss the result of :func:`envgen.solve.solve` is stored under the
    scene's :func:`scene_hash` and returned; on a hit the *identical* cached object
    is returned without recomputing. With a default (``None``) cache this is exactly
    equivalent to calling ``solve(scene)``.
    """
    if cache is None:
        cache = {}
    key = scene_hash(scene)
    if key in cache:
        return cache[key]
    result = solve(scene)
    cache[key] = result
    return result
