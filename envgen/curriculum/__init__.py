"""Curriculum / environment-design subsystem (Stage 5).

Frozen surface: :class:`Level`, the metric registry (:func:`register_metric`/
:func:`get_metric`/:func:`registered_metrics`) in :mod:`envgen.curriculum.base`.
Concrete difficulty metrics live one-per-file under :mod:`.metrics` (auto-discovered);
the ACCEL-style editor loop, PLR-style buffer, dataset emitter, and Gym adapter are
added by Stage 5 tickets as their own modules.
"""
from envgen.curriculum.base import (
    DifficultyMetric,
    Level,
    get_metric,
    register_metric,
    registered_metrics,
)

__all__ = [
    "DifficultyMetric",
    "Level",
    "get_metric",
    "register_metric",
    "registered_metrics",
]
