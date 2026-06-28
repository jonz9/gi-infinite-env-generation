"""Validator — one report from structural + placement + solvability checks.

This is build step 4. It does not re-implement any rule: it *composes* the three
existing layers and returns every problem it finds (so the planner repair loop in
build step 5 gets the full picture in one pass), with a single exception noted
below.

The three layers
----------------
1. **Structural** (:func:`envgen.schema.check_well_formed`): grid shape, tile
   values, unique ids, in-bounds positions, resolvable Key->Door refs, exactly
   one Player.
2. **Placement / overlap** (NEW here — the gap the other layers leave): every
   object must sit on a floor tile, and blocking objects must not collide. See
   the stackability rule below.
3. **Solvability** (:func:`envgen.navigate.validate_solvable`): key-before-door
   reachability + exit reachability, via the shared lazy BFS over
   :meth:`envgen.world.World.neighbors`.

Stackability rule
-----------------
``Player``, ``Key`` and ``Exit`` are non-blocking markers / pickups: they may
freely share a cell (a Player may stand on a Key or an Exit). ``Table`` and
``Door`` are blocking (:data:`envgen.schema.BLOCKING_TYPES`) and must occupy
their cell *exclusively* — no other object, blocking or not, may share a cell
with a blocking object. And nothing may sit on a wall tile.

Ordering note
-------------
Solvability is only checked when there are **no structural errors**: you cannot
meaningfully navigate a malformed grid. Placement errors do not suppress the
solvability pass (the grid itself is still well-formed). All other errors are
collected, never short-circuited.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from envgen.schema import (
    BLOCKING_TYPES,
    SceneGraph,
    SceneObject,
    check_well_formed,
)
from envgen.world import World
from envgen.navigate import validate_solvable


@dataclass
class ValidationReport:
    """The outcome of :func:`validate`.

    ``ok`` is True iff ``errors`` is empty. Each error is a specific, human- and
    LLM-readable string suitable for the planner repair loop.
    """

    ok: bool
    errors: list[str] = field(default_factory=list)


def validate(scene: SceneGraph) -> ValidationReport:
    """Validate ``scene`` across structural, placement, and solvability layers.

    Composes (never duplicates) :func:`envgen.schema.check_well_formed`, the
    placement/overlap checks in this module, and
    :func:`envgen.navigate.validate_solvable`. Returns every problem found;
    solvability is skipped when structural errors exist. See module docstring
    for the stackability rule.
    """
    structural = check_well_formed(scene)
    placement = _check_placement(scene)
    solvability: list[str] = []
    if not structural:  # can't navigate a malformed grid
        ok, msg = validate_solvable(World.from_scene(scene).neighbors, scene.objects)
        if not ok:
            solvability.append(msg)
    errors = structural + placement + solvability
    return ValidationReport(ok=not errors, errors=errors)


def _fmt(pos: tuple[int, int]) -> str:
    """Render a coordinate as ``(x,y)`` for error messages."""
    return f"({pos[0]},{pos[1]})"


def _blocks(obj: SceneObject) -> bool:
    """Whether ``obj`` claims its cell exclusively (a Table or Door)."""
    return obj.type in BLOCKING_TYPES


def _check_placement(scene: SceneGraph) -> list[str]:
    """Check that objects sit on floor tiles and blocking objects don't collide.

    In-bounds is left to :func:`check_well_formed`; we only flag floor/overlap so
    out-of-bounds objects are not double-reported as "on a wall tile".
    """
    errors: list[str] = []
    occupants: dict[tuple[int, int], list[SceneObject]] = {}
    for obj in scene.objects:
        if scene.grid.in_bounds(*obj.pos) and scene.grid.is_wall(*obj.pos):
            errors.append(f"object {obj.id!r} at {_fmt(obj.pos)} is on a wall tile")
        for other in occupants.get(obj.pos, []):
            if _blocks(obj) or _blocks(other):
                errors.append(
                    f"object {obj.id!r} at {_fmt(obj.pos)} overlaps {other.id!r}"
                )
        occupants.setdefault(obj.pos, []).append(obj)
    return errors


if __name__ == "__main__":  # pragma: no cover - quick manual smoke test
    import pathlib
    import sys

    if len(sys.argv) > 1:
        path = pathlib.Path(sys.argv[1])
    else:
        path = pathlib.Path(__file__).resolve().parent.parent / "examples" / "room_key_door.json"
    scene = SceneGraph.from_json(path.read_text())
    report = validate(scene)
    print(f"validating {path.name}: {len(scene.objects)} objects")
    print("ok" if report.ok else "ERRORS:\n  " + "\n  ".join(report.errors))
