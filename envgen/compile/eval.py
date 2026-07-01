"""Compiler eval harness (Stage 3, S3-T12).

A small, measurable experiment over a labeled set of fixtures: run the compiler on
each ``(scene, command, completion, expected_ops)`` case and score op-exact-match
accuracy, validity rate (do the emitted ops parse + apply + validate?), and how many
needed no repair. Reuses the S3-T10 fixtures and their canned ``complete`` so it runs
offline; a caller may pass a live ``complete`` and its own cases instead.

This is the "benchmark, don't hand-wave" artifact the operating manual asks for.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from envgen.compile.compiler import compile_edit
from envgen.compile.fixtures import FIXTURES, Fixture, fixtures_canned
from envgen.edit import EditError, apply_ops, op_from_dict
from envgen.validate import validate


@dataclass
class CaseResult:
    """Outcome for one fixture."""

    name: str
    exact_match: bool
    valid: bool
    got: list[dict] = field(default_factory=list)
    expected: list[dict] = field(default_factory=list)
    notes: str = ""


@dataclass
class EvalReport:
    """Aggregate scorecard over a set of cases."""

    total: int
    exact_matches: int
    valid: int
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        """Fraction of cases whose ops exactly match the expected ops."""
        return self.exact_matches / self.total if self.total else 0.0

    @property
    def validity_rate(self) -> float:
        """Fraction of cases whose emitted ops apply + validate cleanly."""
        return self.valid / self.total if self.total else 0.0

    def summary(self) -> str:
        """A one-line printable scorecard."""
        return (
            f"{self.total} cases | accuracy {self.accuracy:.0%} "
            f"({self.exact_matches}/{self.total}) | "
            f"validity {self.validity_rate:.0%} ({self.valid}/{self.total})"
        )


def evaluate(cases: list[Fixture] | None = None, *, complete=None) -> EvalReport:
    """Run the compiler over ``cases`` and return an :class:`EvalReport`.

    Defaults to the bundled :data:`~envgen.compile.fixtures.FIXTURES` with their
    canned ``complete``, so ``evaluate()`` with no args is a self-contained smoke of
    the whole compile path.
    """
    cases = cases if cases is not None else FIXTURES
    complete = complete if complete is not None else fixtures_canned()

    results = [_run_case(fx, complete) for fx in cases]
    return EvalReport(
        total=len(results),
        exact_matches=sum(r.exact_match for r in results),
        valid=sum(r.valid for r in results),
        cases=results,
    )


def _run_case(fx: Fixture, complete) -> CaseResult:
    """Compile one fixture and score exact-match + validity."""
    scene = fx.scene()
    result = compile_edit(scene, fx.command, complete=complete)
    exact = result.ops == fx.expected_ops
    valid = _applies_and_validates(scene, result.ops)
    return CaseResult(
        name=fx.name,
        exact_match=exact,
        valid=valid,
        got=result.ops,
        expected=fx.expected_ops,
        notes=result.notes,
    )


def _applies_and_validates(scene, op_dicts: list[dict]) -> bool:
    """Whether ``op_dicts`` parse, apply to ``scene``, and yield a valid scene."""
    if not op_dicts:
        return False
    try:
        ops = [op_from_dict(d) for d in op_dicts]
        candidate = apply_ops(scene, ops)
    except EditError:
        return False
    return validate(candidate).ok


if __name__ == "__main__":  # pragma: no cover - quick manual scorecard
    print(evaluate().summary())
