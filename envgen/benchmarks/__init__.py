"""Benchmark suite subsystem (Stage 6).

Frozen surface: :class:`BenchmarkCase` and the case registry in
:mod:`envgen.benchmarks.base`. Concrete cases live one-per-file under :mod:`.cases`
(auto-discovered); the runner/scorecard is a Stage 6 ticket module.
"""
from envgen.benchmarks.base import (
    BenchmarkCase,
    get_case,
    register_case,
    registered_cases,
)

__all__ = ["BenchmarkCase", "get_case", "register_case", "registered_cases"]
