"""Compile repair loop (Stage 3, S3-T05).

The Stage-3 analogue of :mod:`envgen.repair`: compile an NL command to edit ops,
*dry-run* them against the scene, and on failure feed the exact error back into the
prompt and retry — up to ``max_retries`` attempts. Closes the NL→ops loop the same
way the planner repair loop closes NL→scene.

The model seam stays injectable: every attempt goes through
:func:`~envgen.compile.compiler.compile_edit` with the same ``complete``; only the
command text grows (a quoted feedback block is appended), so the loop runs fully
offline in tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from envgen.compile.compiler import compile_edit
from envgen.edit import EditError, apply_ops, op_from_dict
from envgen.schema import SceneGraph
from envgen.validate import validate

#: Prefix for the feedback block appended to the command on each retry.
FEEDBACK_MARKER = "Your previous ops were rejected for these reasons:"


@dataclass
class CompileAttempt:
    """One compile + dry-run trip."""

    ops: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def ok(self) -> bool:
        """Non-empty ops that parse and produce a valid scene."""
        return bool(self.ops) and not self.errors and not self.notes


class CompileRepairError(RuntimeError):
    """Raised when no valid op batch is produced within ``max_retries`` attempts."""

    def __init__(self, attempts: list[CompileAttempt]) -> None:
        self.attempts = attempts
        last = attempts[-1].errors or [attempts[-1].notes or "no ops produced"]
        super().__init__(
            f"could not compile a valid edit in {len(attempts)} attempts; "
            f"last errors: {'; '.join(last)}"
        )


def compile_valid(
    scene: SceneGraph,
    command: str,
    *,
    complete,
    prompt_name: str = "editor_system",
    max_retries: int = 3,
) -> tuple[list[dict], list[CompileAttempt]]:
    """Compile ``command`` to a *valid* op batch, retrying with feedback on failure.

    Returns ``(ops, attempts)`` on success. Raises :class:`CompileRepairError` if no
    attempt yields non-empty ops that apply cleanly and validate within
    ``max_retries``. Success requires a non-empty op batch (an empty diff is treated
    as a failed compile and fed back).
    """
    attempts: list[CompileAttempt] = []
    feedback: str | None = None
    for _ in range(max(1, max_retries)):
        cmd = command if feedback is None else f"{command}\n\n{FEEDBACK_MARKER}\n{feedback}"
        result = compile_edit(scene, cmd, complete=complete, prompt_name=prompt_name)
        errors = _dry_run(scene, result.ops)
        attempt = CompileAttempt(ops=result.ops, errors=errors, notes=result.notes)
        attempts.append(attempt)
        if attempt.ok:
            return result.ops, attempts
        feedback = _feedback(attempt)
    raise CompileRepairError(attempts)


def _dry_run(scene: SceneGraph, op_dicts: list[dict]) -> list[str]:
    """Apply op dicts to ``scene`` and validate; return error strings (empty = ok).

    An empty op batch is itself an error (the compiler produced no diff).
    """
    if not op_dicts:
        return ["no ops were produced; emit at least one edit op"]
    try:
        ops = [op_from_dict(d) for d in op_dicts]
        candidate = apply_ops(scene, ops)
    except EditError as exc:
        return [str(exc)]
    report = validate(candidate)
    return list(report.errors)


def _feedback(attempt: CompileAttempt) -> str:
    """Assemble the feedback string fed back into the next prompt."""
    parts = list(attempt.errors)
    if attempt.notes:
        parts.append(attempt.notes)
    return "; ".join(parts) if parts else "the previous attempt was invalid"
