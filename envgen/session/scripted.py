"""Scripted (headless) session driver — ticket S2-T11.

The deterministic counterpart to the interactive REPL (``harness.py``): instead of
reading typed commands from a TTY, :func:`run_script` walks a *pre-baked list of
steps* through a :class:`~envgen.session.core.HarnessSession` and returns the
:class:`~envgen.session.base.Transcript` for each step. No stdin, no stdout, no
randomness of its own — given the same scene and steps it always produces the same
transcripts, which is exactly what tests and benchmarks need.

Each *step* is one batch of edits (the same all-or-nothing unit ``session.step``
commits or rejects). A step may be given as:

* a single op — an :class:`~envgen.edit.EditOp` or its ``to_dict()`` form, or
* a list of such ops (applied together, atomically).

Ops are passed straight to :meth:`HarnessSession.step`, which already coerces dicts
to ops, re-validates, re-solves and rolls back on failure — this module never
re-implements that policy; it only sequences the steps.
"""
from __future__ import annotations

from typing import Iterable, Sequence, Union

from envgen.edit import EditOp
from envgen.schema import SceneGraph
from envgen.session.base import Transcript
from envgen.session.core import HarnessSession

#: One edit: an EditOp or its serialized dict form.
Op = Union[EditOp, dict]
#: One step: a single op or a batch of ops applied atomically.
Step = Union[Op, Sequence[Op]]


def _as_batch(step: Step) -> list[Op]:
    """Normalize a step into a list of ops (a lone op becomes a 1-op batch)."""
    if isinstance(step, (EditOp, dict)):
        return [step]
    return list(step)


def run_script(
    scene: SceneGraph, steps: Iterable[Step], *, seed: int = 0
) -> list[Transcript]:
    """Run ``steps`` against a fresh session over ``scene``; collect transcripts.

    Parameters
    ----------
    scene:
        The starting world. The session clones on every commit, so the passed
        scene is never mutated.
    steps:
        An ordered iterable of steps. Each step is one op or a list of ops (dicts
        or :class:`EditOp`s) applied as a single atomic batch.
    seed:
        Determinism seed forwarded to the :class:`HarnessSession`.

    Returns
    -------
    list[Transcript]
        One transcript per step, in order — each recording the accepted/rejected
        ops and whether the resulting world stayed valid and solvable.
    """
    _, transcripts = run_script_session(scene, steps, seed=seed)
    return transcripts


def run_script_session(
    scene: SceneGraph, steps: Iterable[Step], *, seed: int = 0
) -> tuple[HarnessSession, list[Transcript]]:
    """Like :func:`run_script` but also return the live session for inspection.

    Convenience for callers (benchmarks, tests) that want the final
    ``session.scene``/``session.log()`` alongside the per-step transcripts.
    """
    session = HarnessSession(scene, seed=seed)
    transcripts: list[Transcript] = []
    for step in steps:
        transcripts.append(session.step(_as_batch(step)))
    return session, transcripts
