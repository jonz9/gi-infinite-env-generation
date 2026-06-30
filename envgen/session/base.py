"""Session subsystem — frozen data contracts for the live, changing world.

⚠️ FROZEN FILE. Do not edit as part of a ticket. Defines the records that flow
through a :class:`HarnessSession` (built in Stage 2 tickets). The session is the
*product*: a persistent world + an op-log that an agent grows and mutates while the
solvability invariant is held. See ``.claude/ARCHITECTURE.md`` and ``tickets/README.md``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional, Protocol, Sequence, runtime_checkable

if TYPE_CHECKING:  # avoid import cost / cycles at runtime
    from envgen.edit.base import EditOp
    from envgen.schema import SceneGraph


@dataclass(frozen=True)
class OpLogEntry:
    """One accepted (or rejected) edit in the session's history.

    ``op`` is the op's ``to_dict()`` form so the log is pure JSON: ``seed + [op...]``
    reproduces the exact world (the determinism invariant). ``scene_hash`` is the
    hash of the resulting scene, for replay verification.
    """

    op: dict[str, Any]
    accepted: bool
    reason: str = ""
    scene_hash: str = ""


@dataclass(frozen=True)
class Transcript:
    """The result of one ``session.step(...)`` — what changed and whether it holds.

    Attributes
    ----------
    applied: op dicts that were accepted and applied this step.
    rejected: ``(op_dict, reason)`` for ops refused to preserve the invariant.
    valid: whether the post-step world passes validation.
    solved: whether the post-step world is still provably solvable.
    errors: validation error strings (feed the NL→ops repair loop).
    render_before / render_after: ASCII snapshots framing the diff.
    note: free-form summary line for REPL/log output.
    """

    applied: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[tuple[dict[str, Any], str]] = field(default_factory=list)
    valid: bool = True
    solved: bool = True
    errors: list[str] = field(default_factory=list)
    render_before: str = ""
    render_after: str = ""
    note: str = ""


@dataclass(frozen=True)
class ReplayCheck:
    """Outcome of replaying an op-log from a seed — determinism proof."""

    ok: bool
    diverged_at: Optional[int] = None
    detail: str = ""


@runtime_checkable
class HarnessSessionProtocol(Protocol):
    """The live-session surface that Stage 2 modules code against.

    Implemented by ``envgen/session/core.py`` (ticket S2-T02). Other Stage 2 tickets
    (guard, stats, branch, history, drivers) accept *any* object satisfying this
    Protocol, so they are decoupled from the concrete implementation and can be built
    in parallel against this frozen contract.
    """

    #: the current, live scene (kept solvable across edits).
    scene: "SceneGraph"
    #: True iff the current scene is provably solvable.
    solved: bool

    def step(self, ops: "Sequence[EditOp]") -> Transcript:
        """Apply ops atomically: validate+solve; accept if the invariant holds, else
        roll back. Returns a :class:`Transcript` describing what changed."""
        ...

    def log(self) -> list[OpLogEntry]:
        """The ordered op-log (accepted + rejected). With the seed, reproduces state."""
        ...
