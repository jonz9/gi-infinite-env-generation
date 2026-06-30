"""Op diff renderer — a human-readable before/after view of one edit.

``diff(before, after) -> str`` produces a stacked ASCII render of both scenes
(reusing :mod:`envgen.render`) plus a concise per-change summary: which grid
cells changed tile value, and which objects were added, removed, or moved (by
id). Pure — it reads the two scenes and never mutates them, and adds no new
dependencies. Used by the session Transcript and the REPL to show what an op did.
"""
from __future__ import annotations

from envgen.render import render_scene
from envgen.schema import SceneGraph, SceneObject


def diff(before: SceneGraph, after: SceneGraph) -> str:
    """Return an ASCII before/after view of two scenes plus a change summary."""
    sections = [
        "--- before ---",
        render_scene(before),
        "--- after ---",
        render_scene(after),
        "--- changes ---",
        *_summary(before, after),
    ]
    return "\n".join(sections)


def _summary(before: SceneGraph, after: SceneGraph) -> list[str]:
    """Concise human-readable lines describing tile, object, and goal changes."""
    lines = _tile_changes(before.grid, after.grid)
    lines += _object_changes(before, after)
    if before.goal != after.goal:
        lines.append(f"goal: {before.goal!r} -> {after.goal!r}")
    return lines or ["(no changes)"]


def _tile_changes(before, after) -> list[str]:
    """One line per cell whose tile value changed (in-bounds for both grids)."""
    changed: list[str] = []
    for y in range(min(before.h, after.h)):
        for x in range(min(before.w, after.w)):
            old, new = before.tiles[y][x], after.tiles[y][x]
            if old != new:
                kind = "wall" if new == 1 else "floor"
                changed.append(f"tile ({x},{y}): -> {kind}")
    extra: list[str] = []
    if (before.w, before.h) != (after.w, after.h):
        extra.append(f"grid: {before.w}x{before.h} -> {after.w}x{after.h}")
    return extra + changed


def _object_changes(before: SceneGraph, after: SceneGraph) -> list[str]:
    """Lines for objects added, removed, moved, or otherwise changed, keyed by id."""
    b = {o.id: o for o in before.objects}
    a = {o.id: o for o in after.objects}
    lines: list[str] = []
    for obj_id in a.keys() - b.keys():
        o = a[obj_id]
        lines.append(f"added {obj_id} ({o.type.value}) at {_pos(o)}")
    for obj_id in b.keys() - a.keys():
        o = b[obj_id]
        lines.append(f"removed {obj_id} ({o.type.value}) from {_pos(o)}")
    for obj_id in sorted(b.keys() & a.keys()):
        lines += _changed_object(b[obj_id], a[obj_id])
    return lines


def _changed_object(old: SceneObject, new: SceneObject) -> list[str]:
    """Describe a moved or prop-changed object that exists in both scenes."""
    lines: list[str] = []
    if tuple(old.pos) != tuple(new.pos):
        lines.append(f"moved {new.id} from {_pos(old)} to {_pos(new)}")
    props = []
    if old.locked != new.locked:
        props.append(f"locked {old.locked} -> {new.locked}")
    if old.opens != new.opens:
        props.append(f"opens {old.opens!r} -> {new.opens!r}")
    if props:
        lines.append(f"{new.id}: " + ", ".join(props))
    return lines


def _pos(obj: SceneObject) -> str:
    """Format an object position as ``(x,y)``."""
    return f"({obj.pos[0]},{obj.pos[1]})"
