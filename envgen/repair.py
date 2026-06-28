"""Repair loop (build step 5): plan -> validate -> feed errors back, retry.

The planner (build step 3) can emit JSON that fails to parse or a scene graph
that the validator (build step 4) rejects as malformed/unsolvable. This module
closes the loop: on any failure it builds an *augmented* user prompt that quotes
the specific feedback (a :class:`~envgen.schema.SchemaError` message or the
:class:`~envgen.validate.ValidationReport` errors) and calls the planner again,
up to ``max_retries`` total attempts.

The model call stays injectable: :func:`plan_valid` threads the same ``complete``
seam through every :func:`envgen.planner.plan` call (only the user prompt grows),
so the whole loop runs fully offline in tests. See ``tests/test_repair.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from envgen import planner
from envgen.planner import Complete
from envgen.schema import SceneGraph, SchemaError
from envgen.validate import validate

# Marker prefixing the feedback block appended on each retry. Tests (and a
# branching ``complete`` seam) can look for it to detect a repair attempt.
FEEDBACK_MARKER = "Your previous attempt was invalid for these reasons:"


@dataclass
class Attempt:
    """One trip through plan + validate.

    Attributes
    ----------
    scene: The parsed scene graph, or ``None`` if planning/parsing failed.
    errors: Validation error strings (empty when ``raw_error`` is set or when
        the attempt succeeded).
    raw_error: A :class:`~envgen.schema.SchemaError`/JSON message when the model
        output did not even parse; ``None`` otherwise.
    """

    scene: SceneGraph | None
    errors: list[str] = field(default_factory=list)
    raw_error: str | None = None

    @property
    def ok(self) -> bool:
        """Whether this attempt produced a valid scene (no errors, no raw error)."""
        return self.scene is not None and not self.errors and self.raw_error is None

    def feedback(self) -> str:
        """The failure feedback for this attempt, as a single string."""
        if self.raw_error is not None:
            return self.raw_error
        return "; ".join(self.errors)


class RepairError(RuntimeError):
    """Raised when no valid scene is produced within ``max_retries`` attempts.

    The message includes the attempt count and the last attempt's feedback so
    callers (and logs) see why the loop gave up.
    """


def _attempt(prompt: str, complete: Complete | None, model: str) -> Attempt:
    """Run one plan + validate pass, capturing any failure as an :class:`Attempt`."""
    try:
        scene = planner.plan(prompt, complete=complete, model=model)
    except SchemaError as exc:
        return Attempt(scene=None, errors=[], raw_error=str(exc))
    report = validate(scene)
    return Attempt(scene=scene, errors=list(report.errors), raw_error=None)


def _augment(prompt: str, attempt: Attempt) -> str:
    """Append the failed ``attempt``'s feedback to ``prompt`` for a retry."""
    return (
        f"{prompt}\n\n{FEEDBACK_MARKER} {attempt.feedback()}\n"
        "Fix them and output a corrected single JSON scene."
    )


def plan_valid(
    prompt: str,
    *,
    complete: Complete | None = None,
    max_retries: int = 3,
    model: str = "claude-opus-4-8",
) -> tuple[SceneGraph, list[Attempt]]:
    """Plan a *validated* scene graph, repairing via planner feedback on failure.

    Calls :func:`envgen.planner.plan` (threading the injectable ``complete``
    seam) and runs :func:`envgen.validate.validate` on the result. On any
    failure -- a :class:`~envgen.schema.SchemaError` (bad JSON/schema) or a
    non-empty :class:`~envgen.validate.ValidationReport` -- it appends the
    specific feedback to the user prompt and retries, up to ``max_retries``
    total attempts.

    Returns the first valid :class:`~envgen.schema.SceneGraph` together with the
    full attempt log. Raises :class:`RepairError` if still invalid after
    ``max_retries`` attempts.
    """
    if max_retries < 1:
        raise ValueError(f"max_retries must be >= 1, got {max_retries}")
    attempts: list[Attempt] = []
    current_prompt = prompt
    for _ in range(max_retries):
        attempt = _attempt(current_prompt, complete, model)
        attempts.append(attempt)
        if attempt.ok:
            assert attempt.scene is not None  # narrow for type-checkers
            return attempt.scene, attempts
        current_prompt = _augment(prompt, attempt)
    last = attempts[-1]
    raise RepairError(
        f"no valid scene after {len(attempts)} attempt(s); "
        f"last failure: {last.feedback()}"
    )
