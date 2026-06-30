"""Op-log collection + stable scene hashing (Stage 2, ticket S2-T01).

The op-log is the spine of replay: ``seed + [OpLogEntry...]`` reproduces the exact
world. :class:`OpLog` wraps the ordered list of :class:`OpLogEntry` records with
JSON round-tripping, and :func:`scene_hash` gives a deterministic content hash of a
scene so replay can be verified hash-for-hash. Pure stdlib.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import TYPE_CHECKING, Iterator

from envgen.session.base import OpLogEntry

if TYPE_CHECKING:  # avoid import cost / cycles at runtime
    from envgen.schema import SceneGraph


class OpLog:
    """An ordered, JSON-serializable collection of :class:`OpLogEntry`."""

    def __init__(self, entries: list[OpLogEntry] | None = None) -> None:
        self._entries: list[OpLogEntry] = list(entries or [])

    # -- collection surface -------------------------------------------------
    def append(self, entry: OpLogEntry) -> None:
        """Append one accepted/rejected entry to the end of the log."""
        if not isinstance(entry, OpLogEntry):
            raise TypeError(f"OpLog.append expects OpLogEntry, got {type(entry).__name__}")
        self._entries.append(entry)

    def __iter__(self) -> Iterator[OpLogEntry]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __getitem__(self, index: int) -> OpLogEntry:
        return self._entries[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, OpLog):
            return self._entries == other._entries
        return NotImplemented

    def __repr__(self) -> str:
        return f"OpLog({self._entries!r})"

    @property
    def entries(self) -> list[OpLogEntry]:
        """A shallow copy of the underlying entry list."""
        return list(self._entries)

    # -- (de)serialization --------------------------------------------------
    def to_json(self, *, indent: int | None = None) -> str:
        """Serialize the whole log to a JSON array string."""
        return json.dumps([asdict(e) for e in self._entries], indent=indent)

    @classmethod
    def from_json(cls, text: str) -> "OpLog":
        """Parse a log from :meth:`to_json` output; round-trips to an equal log."""
        data = json.loads(text)
        entries = [
            OpLogEntry(
                op=d["op"],
                accepted=d["accepted"],
                reason=d.get("reason", ""),
                scene_hash=d.get("scene_hash", ""),
            )
            for d in data
        ]
        return cls(entries)


def scene_hash(scene: "SceneGraph") -> str:
    """Stable content hash of ``scene``.

    Hashes ``scene.to_dict()`` serialized as canonical JSON (``sort_keys=True``,
    compact separators) so the digest is stable across runs and equal for equal
    scenes. Returns a blake2b hexdigest.
    """
    canonical = json.dumps(scene.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode("utf-8")).hexdigest()
