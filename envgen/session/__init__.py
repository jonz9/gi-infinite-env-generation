"""Session subsystem — the persistent, changing world (Stage 2).

Frozen public surface here is only the data contracts in :mod:`envgen.session.base`.
The concrete :class:`HarnessSession`, op-log, incremental verifier/solver wrappers,
and drivers are added by Stage 2 tickets as their own modules (``core.py``,
``oplog.py``, ...) and imported directly by their consumers — so this file stays
frozen as tickets land.
"""
from envgen.session.base import (
    HarnessSessionProtocol,
    OpLogEntry,
    ReplayCheck,
    Transcript,
)

__all__ = ["HarnessSessionProtocol", "OpLogEntry", "ReplayCheck", "Transcript"]
