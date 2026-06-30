"""Benchmark suite — frozen registry of named environment cases (Stage 6).

⚠️ FROZEN FILE. Do not edit as part of a ticket. A benchmark case is a small,
self-contained scenario the harness must handle (generate / change / stay solvable).
Tickets add cases under ``benchmarks/cases/`` (self-registering); the runner iterates
the registry. See ``tickets/README.md``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from envgen.schema import SceneGraph

# A case builder returns the scene to evaluate. (Live-edit cases may instead drive a
# session; such cases expose that via their own module and still register a builder
# returning the final/initial scene for the runner's solvability check.)
SceneBuilder = Callable[[], SceneGraph]


@dataclass(frozen=True)
class BenchmarkCase:
    """One named scenario the harness is scored on.

    Attributes
    ----------
    name: registry key (e.g. ``"locked_door"``).
    build: returns the :class:`~envgen.schema.SceneGraph` under test.
    expect_solved: whether the runner should expect SOLVED (False for known-unsolvable
        negative cases that must be *rejected*).
    description: one-line summary. tags: free-form grouping.
    """

    name: str
    build: SceneBuilder
    expect_solved: bool = True
    description: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


_CASES: dict[str, BenchmarkCase] = {}


def register_case(case: BenchmarkCase) -> BenchmarkCase:
    """Register a :class:`BenchmarkCase`. Raises on duplicate names."""
    if case.name in _CASES and _CASES[case.name] is not case:
        raise ValueError(f"benchmark case {case.name!r} already registered")
    _CASES[case.name] = case
    return case


def get_case(name: str) -> BenchmarkCase:
    _discover()
    if name not in _CASES:
        valid = ", ".join(sorted(_CASES)) or "(none)"
        raise KeyError(f"unknown benchmark case {name!r}; registered: {valid}")
    return _CASES[name]


def registered_cases() -> dict[str, BenchmarkCase]:
    _discover()
    return dict(_CASES)


def _discover() -> None:
    from envgen.benchmarks import cases as _c  # noqa: F401
