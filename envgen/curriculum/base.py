"""Curriculum / environment-design — frozen contracts (Stage 5).

⚠️ FROZEN FILE. Do not edit as part of a ticket. The RL engineering here lives on
the *generator* side: GI has the vision policy; we supply environments + an exact
difficulty signal. Because BFS (:func:`envgen.solve.solve`) yields the optimal
solution, difficulty/regret is computed *exactly and for free* — no trained net.
Tickets add metrics under ``curriculum/metrics/`` (self-registering) and loop/buffer/
dataset modules as their own files. See ``.claude/ARCHITECTURE.md`` §8 and
``tickets/README.md``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from envgen.schema import SceneGraph


@dataclass(frozen=True)
class Level:
    """A candidate environment plus its provenance (for reproducible datasets).

    ``seed + oplog`` reproduce the exact ``scene`` (the determinism invariant), so a
    level is a small hashable artifact. ``meta`` carries cached signals (e.g. an
    already-computed solve result) to avoid recomputation.
    """

    scene: SceneGraph
    seed: int = 0
    oplog: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


# A difficulty metric maps a Level to a scalar (higher = harder). Exact, BFS-derived.
DifficultyMetric = Callable[[Level], float]

_METRICS: dict[str, DifficultyMetric] = {}


def register_metric(name: str, metric: DifficultyMetric) -> DifficultyMetric:
    """Register a difficulty metric under ``name``. Raises on duplicate names."""
    if name in _METRICS and _METRICS[name] is not metric:
        raise ValueError(f"difficulty metric {name!r} already registered")
    _METRICS[name] = metric
    return metric


def get_metric(name: str) -> DifficultyMetric:
    _discover()
    if name not in _METRICS:
        valid = ", ".join(sorted(_METRICS)) or "(none)"
        raise KeyError(f"unknown metric {name!r}; registered: {valid}")
    return _METRICS[name]


def registered_metrics() -> dict[str, DifficultyMetric]:
    _discover()
    return dict(_METRICS)


def _discover() -> None:
    """Import the metrics package so each metric module self-registers."""
    from envgen.curriculum import metrics as _m  # noqa: F401
