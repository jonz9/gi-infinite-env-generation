"""Session persistence — save/load a :class:`HarnessSession` as JSON (ticket S2-T07).

A session's identity is its **seed**, its **scene**, and its **op-log**. This module
serializes those to a JSON string with :func:`save` and reconstructs an equivalent
live session with :func:`load`, such that the round-trip
``load(save(session))`` yields a session whose ``.scene`` hashes identically and
whose ``log()`` is preserved entry-for-entry (the determinism invariant, made
durable).

Storage choice
--------------
The ticket's *preferred* form is ``seed + initial scene + op-log`` reconstructed by
**replay**. That requires the concrete session to expose its *initial* scene so the
log can be replayed from it. The landed ``envgen/session/core.py`` exposes only the
**live** ``scene`` and ``seed`` (not an initial snapshot), and its log interleaves
accepted *and* rejected ops — so replaying from an initial state is not available
through the frozen surface. We therefore use the spec's documented fallback: store
``seed + current scene + log()`` and reconstruct a session whose ``.scene`` is byte
-identical and whose log is restored verbatim. No sibling Stage-2 module is imported;
the scene hash used for verification is computed here from canonical JSON.

The format is versioned (``"version": 1``) so a future replay-based encoder can be
added without breaking existing payloads.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from envgen.schema import SceneGraph
from envgen.session.base import OpLogEntry
from envgen.session.core import HarnessSession

FORMAT_VERSION = 1


def scene_hash(scene: SceneGraph) -> str:
    """Stable hash of a scene's canonical JSON (local; no sibling imports)."""
    canonical = json.dumps(scene.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _entry_to_dict(entry: OpLogEntry) -> dict[str, Any]:
    """Serialize one :class:`OpLogEntry` to a plain JSON-able dict."""
    return {
        "op": entry.op,
        "accepted": entry.accepted,
        "reason": entry.reason,
        "scene_hash": entry.scene_hash,
    }


def _entry_from_dict(data: dict[str, Any]) -> OpLogEntry:
    """Rebuild one :class:`OpLogEntry` from its serialized dict."""
    return OpLogEntry(
        op=data["op"],
        accepted=bool(data["accepted"]),
        reason=data.get("reason", ""),
        scene_hash=data.get("scene_hash", ""),
    )


def save(session: HarnessSession, *, indent: int | None = 2) -> str:
    """Serialize ``session`` to a JSON string (``seed + scene + op-log``)."""
    payload = {
        "version": FORMAT_VERSION,
        "seed": session.seed,
        "scene": session.scene.to_dict(),
        "log": [_entry_to_dict(e) for e in session.log()],
    }
    return json.dumps(payload, indent=indent)


def load(text: str) -> HarnessSession:
    """Reconstruct a :class:`HarnessSession` from :func:`save` output.

    The returned session's ``.scene`` is identical to the saved one (same hash) and
    its ``log()`` is restored verbatim. Raises :class:`ValueError` on a malformed or
    unsupported payload.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"persist.load: invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"persist.load: expected a JSON object, got {type(data).__name__}")

    version = data.get("version")
    if version != FORMAT_VERSION:
        raise ValueError(
            f"persist.load: unsupported format version {version!r} "
            f"(expected {FORMAT_VERSION})"
        )
    for key in ("seed", "scene", "log"):
        if key not in data:
            raise ValueError(f"persist.load: payload missing required field {key!r}")

    scene = SceneGraph.from_dict(data["scene"])
    session = HarnessSession(scene, seed=int(data["seed"]))
    # Restore the op-log verbatim. The constructor starts an empty log; the saved
    # scene is already the materialized result of those ops, so we re-attach the
    # recorded history rather than re-applying it.
    session._log = [_entry_from_dict(e) for e in data["log"]]
    return session
